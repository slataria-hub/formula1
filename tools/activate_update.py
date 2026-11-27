"""Manage a PRIVATE draft preview. Never publish or alter browser storage."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from audit_championships import audit
from build_preview import ASSETS
from check_update import check_update
from prepare_update import user_payload
from validate_data import ROOT, read, validate


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('invalid number: '+value)))


def sports_digest(data):
    # Provenance alone does not justify replacing a working preview. Keep every
    # other field, including session status, schedule, aliases, entrant, laps.
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != 'sourceIds'}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return digest(json_bytes(strip({k: v for k, v in data.items() if k != 'sources'})))


def atomic_write(path, raw):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def private_path(path):
    path = Path(path).resolve()
    if (ROOT/'private').resolve() not in path.parents:
        raise ValueError('managed paths must be inside project private/')
    return path


def draft(raw):
    data = parse(raw)
    if data.get('datasetStatus') != 'draft' or not data.get('events'):
        raise ValueError('nonempty DRAFT required')
    if not any(s['provider'] == 'F1DB' for s in data.get('sources', [])):
        raise ValueError('F1DB source required')
    errors = validate(data)
    if errors:
        raise ValueError('structural validation: ' + str(errors[:5]))
    return data


def checked_audit(data):
    result = audit(data)
    if result['issues']:
        raise ValueError('audit blocked: ' + str(result['issues'][:5]))
    return {json_bytes(x) for x in result['countbackReviewCandidates']}


class Managed:
    def __init__(self, path):
        self.root = private_path(path)
        self.site = self.root/'site'
        self.active = self.site/'official.json'
        self.backups = self.root/'backups'
        self.journal = self.root/'journal'
        self.lock = self.root/'update.lock'

    def initialize(self, baseline):
        raw = Path(baseline).read_bytes()
        checked_audit(draft(raw))
        if self.root.exists():
            raise FileExistsError('managed directory already exists')
        self.root.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix='.managed-', dir=self.root.parent))
        try:
            for name in ('site', 'backups', 'journal'):
                (tmp/name).mkdir()
            for name in ASSETS:
                shutil.copyfile(ROOT/'web'/'preview'/name, tmp/'site'/name)
            atomic_write(tmp/'site'/'official.json', raw)
            # Exact baseline bytes are required by prepare_update's hash gate.
            atomic_write(tmp/'journal'/'initial.json', json_bytes(dict(
                status='initialized', afterSha256=digest(raw), at=stamp(), publicationAuthorized=False)))
            if self.root.exists():
                raise FileExistsError('managed directory already exists')
            tmp.rename(self.root)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
        return digest(raw)

    @contextmanager
    def locked(self):
        for p in (self.root, self.site, self.backups, self.journal):
            if not p.is_dir() or p.is_symlink() or p.resolve() != p:
                raise ValueError('invalid managed directory: ' + str(p))
        if not self.active.is_file() or self.active.is_symlink():
            raise ValueError('invalid active official.json')
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError('update lock exists; another process or interrupted run') from exc
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid())+' '+stamp()+'\n')
            self.recover()
            yield
        finally:
            self.lock.unlink()

    def record(self, path, report):
        atomic_write(path, json_bytes(report))

    def recover(self):
        # A crash can occur between replacing active and committing the journal.
        # The active file hash, not a guessed status, determines recovery.
        pending = [(p, read(p)) for p in self.journal.glob('*.json')]
        pending = [(p, r) for p, r in pending if r['status'] == 'pending']
        if len(pending) > 1:
            raise ValueError('multiple pending transactions; manual inspection required')
        for p, r in pending:
            actual = digest(self.active.read_bytes())
            if actual == r['afterSha256']:
                r['status'] = 'recovered_committed'
            elif actual == r['beforeSha256']:
                r['status'] = 'recovered_not_committed'
            else:
                raise ValueError('pending transaction: active hash not recognized; manual inspection required')
            r['recoveredAt'] = stamp()
            self.record(p, r)

    def save_backup(self, raw):
        h = digest(raw)
        path = self.backups/(h+'.json')
        if path.exists():
            if path.is_symlink() or digest(path.read_bytes()) != h:
                raise ValueError('backup corrupted: '+h)
        else:
            atomic_write(path, raw)
        return h

    def switch(self, old_raw, new_raw, action, user_check):
        before, after = digest(old_raw), digest(new_raw)
        if digest(self.active.read_bytes()) != before:
            raise ValueError('active changed during check; retry from current baseline')
        self.save_backup(old_raw)
        entry = self.journal/(uuid.uuid4().hex+'.json')
        report = dict(action=action, status='pending', beforeSha256=before, afterSha256=after,
                      at=stamp(), publicationAuthorized=False, userCheck=user_check)
        self.record(entry, report)
        try:
            atomic_write(self.active, new_raw)
            if digest(self.active.read_bytes()) != after:
                raise ValueError('active checksum mismatch after replacement')
        except Exception:
            # If a write failed before replacement the active file is unchanged.
            # If a post-replacement verification failed, restore the exact backup.
            if digest(self.active.read_bytes()) != before:
                atomic_write(self.active, old_raw)
                if digest(self.active.read_bytes()) != before:
                    raise RuntimeError('rollback verification failed; inspect journal and backup')
            report['status'] = 'rolled_back'
            self.record(entry, report)
            raise
        # If recording completion fails, leave pending for recovery next run.
        report['status'] = 'committed'
        self.record(entry, report)
        return report

    def activate(self, run, user=None):
        run = private_path(run)
        with self.locked():
            old_raw = self.active.read_bytes()
            new_raw = (run/'candidate.json').read_bytes()
            report = read(run/'update-report.json')
            if (report.get('status'), report.get('stage'), report.get('activated'), report.get('publicationAuthorized')) != ('draft_ready', 'complete', False, False):
                raise ValueError('completed, non-published draft report required')
            if report.get('baselineSha256') != digest(old_raw):
                raise ValueError('stale baseline: prepare again against active official.json')
            if report.get('candidateSha256') != digest(new_raw):
                raise ValueError('candidate checksum mismatch')
            if report.get('audit', {}).get('issues') != 0:
                raise ValueError('report has audit issues')
            old, new = draft(old_raw), draft(new_raw)
            store = read(user) if user else None
            payload = user_payload(store, old, new)
            if payload is not None and (validate(old, payload) or validate(new, payload)):
                raise ValueError('user references invalid')
            errors = check_update(old, new, payload)
            if errors:
                raise ValueError('compatibility blocked: '+str(errors[:5]))
            old_review, new_review = checked_audit(old), checked_audit(new)
            if new_review-old_review:
                raise ValueError('new countback review candidates; manual review required')
            user_check = 'supplied export validated; not modified' if user else 'not supplied; browser storage not accessed'
            if sports_digest(old) == sports_digest(new):
                result = dict(action='activate', status='no_change', beforeSha256=digest(old_raw),
                              afterSha256=digest(old_raw), candidateSha256=digest(new_raw), at=stamp(),
                              userCheck=user_check, publicationAuthorized=False)
                self.record(self.journal/(uuid.uuid4().hex+'.json'), result)
                return result
            return self.switch(old_raw, new_raw, 'activate', user_check)

    def rollback(self, target, expected, user=None):
        if not re.fullmatch(r'[0-9a-f]{64}', target) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError('SHA256 must be 64 lowercase hexadecimal characters')
        with self.locked():
            old_raw = self.active.read_bytes()
            if digest(old_raw) != expected:
                raise ValueError('active hash changed; rollback refused')
            p = self.backups/(target+'.json')
            if not p.is_file() or p.is_symlink():
                raise ValueError('backup not found')
            new_raw = p.read_bytes()
            if digest(new_raw) != target:
                raise ValueError('backup checksum mismatch')
            old, new = draft(old_raw), draft(new_raw)
            checked_audit(new)
            if user:
                payload = user_payload(read(user), old, new)
                if validate(old, payload) or validate(new, payload):
                    raise ValueError('rollback would invalidate supplied user data')
            if expected == target:
                raise ValueError('backup already active')
            return self.switch(old_raw, new_raw, 'rollback', 'supplied export validated; not modified' if user else 'not supplied; browser storage not accessed')

    def status(self):
        with self.locked():
            raw = self.active.read_bytes()
            return dict(activeSha256=digest(raw), backups=sorted(p.stem for p in self.backups.glob('*.json')),
                        site=str(self.site), publicationAuthorized=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='private/managed-preview')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('--baseline', required=True)
    act = sub.add_parser('activate'); act.add_argument('--run', required=True); act.add_argument('--user')
    rb = sub.add_parser('rollback'); rb.add_argument('--sha256', required=True); rb.add_argument('--expected-active', required=True); rb.add_argument('--user')
    sub.add_parser('status')
    args = parser.parse_args()
    try:
        managed = Managed(args.root)
        if args.command == 'init':
            result = dict(status='initialized', activeSha256=managed.initialize(args.baseline), site=str(managed.site), publicationAuthorized=False)
        elif args.command == 'activate':
            result = managed.activate(args.run, args.user)
        elif args.command == 'rollback':
            result = managed.rollback(args.sha256, args.expected_active, args.user)
        else:
            result = managed.status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('LOCAL DRAFT ONLY; NO PUBLICATION AUTHORIZED')
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print('ACTIVATION BLOCKED OR INCOMPLETE:', exc)
        print('Inspect status/journal before retrying; no publication authorized.')
        return 1
    except KeyboardInterrupt:
        print('INTERRUPTED; inspect status/journal; no publication authorized')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
