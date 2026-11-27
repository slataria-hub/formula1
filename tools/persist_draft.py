"""Persist audited DRAFT data on f1-data; never deploy or change the code branch."""
import argparse
import base64
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess

from activate_update import digest, draft, checked_audit, json_bytes, parse, private_path, sports_digest, stamp
from cloud_update import SEED, SEED_SPORTS, rehearse
from validate_data import ROOT, read

REF = 'refs/heads/f1-data'
FILES = {'official.json', 'manifest.json'}
MAX_BYTES = 90 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}')
TAG = re.compile(r'v(\d+)\.(\d+)\.(\d+)')


def tag_tuple(tag):
    m = TAG.fullmatch(tag)
    if not m:
        raise ValueError('invalid release tag')
    return tuple(map(int, m.groups()))


def release_record(release):
    tag, sha = release['tag'], release['sha256']
    tag_tuple(tag)
    if not HEX.fullmatch(sha):
        raise ValueError('invalid release SHA256')
    return {'tag': tag, 'sha256': sha}


def manifest(raw, release, parent):
    if len(raw) >= MAX_BYTES:
        raise ValueError('database near GitHub single-file limit; storage migration required')
    data = draft(raw)
    return dict(version=1, datasetStatus='draft', publicationAuthorized=False,
                independentVerification='pending', officialSha256=digest(raw),
                sportsSha256=sports_digest(data), release=release_record(release),
                parentCommit=parent, storedAt=stamp(), attribution='F1DB (https://github.com/f1db/f1db), CC BY 4.0; transformed by F1 Analytics')


def verify(raw, meta):
    if len(raw) >= MAX_BYTES:
        raise ValueError('stored database exceeds storage limit')
    if (meta.get('version'), meta.get('datasetStatus'), meta.get('publicationAuthorized'), meta.get('independentVerification')) != (1, 'draft', False, 'pending'):
        raise ValueError('invalid DRAFT manifest')
    if meta.get('officialSha256') != digest(raw):
        raise ValueError('stored database checksum mismatch')
    data = draft(raw)
    if sports_digest(data) != meta.get('sportsSha256'):
        raise ValueError('stored sporting checksum mismatch')
    release_record(meta['release'])
    return data


class Store:
    def __init__(self, repo=ROOT):
        self.repo = Path(repo)
        self.env = os.environ.copy()
        self.env.update(GIT_AUTHOR_NAME='F1 Analytics DRAFT', GIT_AUTHOR_EMAIL='f1-draft@users.noreply.github.com',
                        GIT_COMMITTER_NAME='F1 Analytics DRAFT', GIT_COMMITTER_EMAIL='f1-draft@users.noreply.github.com')
        # Restrict the ephemeral CI token to the verified origin; no credentials in command line or config file.
        token = self.env.pop('F1_DATA_GIT_TOKEN', '')
        self.env.pop('F1DB_GITHUB_TOKEN', None)
        if token:
            expected = 'https://github.com/' + os.environ['GITHUB_REPOSITORY']
            urls = [self.git('remote', 'get-url', 'origin').decode().strip(),
                    self.git('remote', 'get-url', '--push', 'origin').decode().strip()]
            if any(url not in (expected, expected+'.git') for url in urls):
                raise ValueError('unexpected CI git origin')
            auth = base64.b64encode(('x-access-token:'+token).encode()).decode()
            self.env.update(GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                            GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+auth,
                            GIT_CONFIG_KEY_1='http.followRedirects', GIT_CONFIG_VALUE_1='false', GIT_TERMINAL_PROMPT='0')

    def call(self, *args, data=None):
        return subprocess.run(['git', '-C', str(self.repo), *args], input=data, capture_output=True,
                              env=self.env, timeout=180, check=False)

    def git(self, *args, data=None):
        p = self.call(*args, data=data)
        if p.returncode:
            # Avoid leaking auth headers or remote credentials into diagnostic output.
            raise ValueError('git '+args[0]+' failed (exit '+str(p.returncode)+'); inspect repository permissions/connection')
        return p.stdout

    def remote_head(self):
        p = self.call('ls-remote', '--exit-code', 'origin', REF)
        if p.returncode == 2:
            return None
        if p.returncode:
            raise ValueError('cannot read remote f1-data')
        fields = p.stdout.decode().split()
        if len(fields)!=2 or fields[1]!=REF or not re.fullmatch(r'[0-9a-f]{40}', fields[0]):
            raise ValueError('unexpected remote ref')
        return fields[0]

    def load(self):
        head = self.remote_head()
        if head is None:
            raise ValueError('f1-data absent; explicit one-time bootstrap required (never auto-reset)')
        self.git('fetch', '--no-tags', 'origin', REF)
        fetched = self.git('rev-parse', 'FETCH_HEAD').decode().strip()
        if fetched != head:
            raise ValueError('f1-data changed during read; rerun')
        names = set(self.git('ls-tree', '--name-only', head).decode().splitlines())
        if names != FILES:
            raise ValueError('unexpected files in f1-data')
        for name in FILES:
            if not self.git('ls-tree', head, '--', name).startswith(b'100644 blob '):
                raise ValueError('invalid stored file type')
        raw = self.git('show', head+':official.json')
        meta = parse(self.git('show', head+':manifest.json'))
        verify(raw, meta)
        parents = self.git('rev-list', '--parents', '-n', '1', head).decode().split()[1:]
        if parents != ([meta['parentCommit']] if meta.get('parentCommit') else []):
            raise ValueError('stored manifest parent does not match git history')
        return head, raw, meta

    def save(self, raw, meta, expected):
        verify(raw, meta)
        if meta.get('parentCommit') != expected:
            raise ValueError('manifest parent mismatch')
        if self.remote_head() != expected:
            raise ValueError('f1-data changed; refusing stale write')
        blobs = {name:self.git('hash-object', '-w', '--stdin', data=value).decode().strip()
                 for name,value in [('official.json',raw),('manifest.json',json_bytes(meta))]}
        tree_input = ''.join('100644 blob '+blobs[name]+'\t'+name+'\n' for name in sorted(blobs)).encode()
        tree = self.git('mktree', data=tree_input).decode().strip()
        args = ['commit-tree', tree] + (['-p', expected] if expected else [])
        commit = self.git(*args, data=('F1 DRAFT '+meta['release']['tag']+'\n').encode()).decode().strip()
        # Exact lease is compare-and-swap, including empty ref on first creation. The new commit
        # always has the expected remote head as its sole parent: no history rewrite.
        self.git('push', '--force-with-lease='+REF+':'+(expected or ''), 'origin', commit+':'+REF)
        if self.remote_head() != commit:
            raise ValueError('remote head changed after push; inspect f1-data before retry')
        return commit


def bootstrap(store, baseline):
    if store.remote_head() is not None:
        raise ValueError('f1-data already exists; bootstrap refused')
    raw = Path(baseline).read_bytes()
    data = draft(raw)
    if sports_digest(data) != SEED_SPORTS:
        raise ValueError('initial baseline does not match pinned sporting reference')
    checked_audit(data)
    return store.save(raw, manifest(raw, SEED, None), None)


def check_release(old, new):
    old, new = release_record(old), release_record(new)
    if tag_tuple(new['tag']) < tag_tuple(old['tag']):
        raise ValueError('release downgrade refused')
    if old['tag'] == new['tag'] and old['sha256'] != new['sha256']:
        raise ValueError('same release tag has different archive hash; review required')


def update(store, output, *, release_json=None, local_archive=None, as_of=None):
    output = private_path(output)
    if output.exists():
        raise FileExistsError('output already exists; use a fresh run directory')
    try:
        return _update(store, output, release_json=release_json, local_archive=local_archive, as_of=as_of)
    except Exception as exc:
        reports = output/'reports'
        reports.mkdir(parents=True, exist_ok=True)
        (reports/'persistence.json').write_bytes(json_bytes(dict(status='blocked', error=str(exc),
            publicationAuthorized=False, note='inspect remote status before retry if a push was attempted')))
        raise


def _update(store, output, *, release_json=None, local_archive=None, as_of=None):
    head, raw, meta = store.load()
    result = rehearse(output, baseline_raw=raw, release_json=release_json, local_archive=local_archive, as_of=as_of)
    report = read(output/'reports/update/update-report.json')
    check_release(meta['release'], report['release'])
    if result['publicationAuthorized'] is not False or result['status'] != 'draft_ready':
        raise ValueError('invalid rehearsal state')
    active = (output/'disposable-managed/site/official.json').read_bytes()
    if digest(active) != result['activeSha256']:
        raise ValueError('active checksum mismatch')
    if result['rehearsal'] == 'no_change':
        if active != raw or store.remote_head() != head:
            raise ValueError('no-change verification failed or remote advanced')
        status, commit = 'no_change', head
    elif result['rehearsal'] == 'committed':
        if digest(active) != report['candidateSha256']:
            raise ValueError('candidate checksum mismatch')
        commit = store.save(active, manifest(active, report['release'], head), head)
        status = 'stored'
    else:
        raise ValueError('unknown rehearsal result')
    summary = dict(status=status, beforeCommit=head, afterCommit=commit, officialSha256=digest(active),
                   observedRelease=release_record(report['release']), publicationAuthorized=False, independentVerification='pending')
    (output/'reports/persistence.json').write_bytes(json_bytes(summary))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('bootstrap'); b.add_argument('--baseline', required=True)
    u = sub.add_parser('update'); u.add_argument('--output', required=True); u.add_argument('--release-json'); u.add_argument('--local-archive'); u.add_argument('--as-of',type=date.fromisoformat)
    sub.add_parser('status')
    a = p.parse_args()
    try:
        store = Store()
        if a.command == 'bootstrap':
            r = dict(status='initialized', commit=bootstrap(store,a.baseline), publicationAuthorized=False)
        elif a.command == 'status':
            head, _, meta = store.load(); r = dict(commit=head, manifest=meta)
        else:
            r = update(store,a.output,release_json=a.release_json,local_archive=a.local_archive,as_of=a.as_of)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print('PERSISTENT DRAFT ONLY; NO PUBLICATION AUTHORIZED')
        return 0
    except Exception as exc:
        print('DRAFT STORAGE BLOCKED:', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
