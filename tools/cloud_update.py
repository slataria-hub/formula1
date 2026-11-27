"""Run a disposable F1DB DRAFT rehearsal, never publish or retain active state."""
import argparse
import json
from datetime import date
from pathlib import Path

from activate_update import Managed, digest, private_path, sports_digest
from fetch_f1db import acquire
from import_f1db import import_archive, write_new
from prepare_update import prepare
from reconcile_f1db import reconcile
from review_remaining import correct

# Immutable initial reference, NOT a limit on the latest season or release.
SEED = dict(tag='v2026.21.0',
            url='https://github.com/f1db/f1db/releases/download/v2026.21.0/f1db-csv.zip',
            sha256='8c33f41f7e095e995634305a33b28bd8638366056f877109ffc290d06d341950',
            size=4513594, publishedAt='2026-11-22T11:10:50Z')
SEED_DATE = date(2026, 11, 27)
SEED_SPORTS = '6433d246464a8980e2f17c92b4aff02ca12c9052c026c8bdb328f7c791662a46'


def make_baseline(output, cache, seed_archive=None):
    archive, state = acquire(SEED, cache, local_archive=seed_archive)
    raw, imported = import_archive(archive, from_season=2000, as_of=SEED_DATE, revision=SEED['tag'])
    if imported['archiveSha256'] != SEED['sha256']:
        raise ValueError('reference archive changed during import')
    data = correct(reconcile(raw)[0])[0]
    if sports_digest(data) != SEED_SPORTS:
        raise ValueError('reference sporting fingerprint mismatch; review seed reconstruction')
    write_new(output, data)
    return state


def rehearse(output, *, seed_archive=None, release_json=None, local_archive=None, as_of=None, baseline_raw=None):
    output = private_path(output)
    if bool(release_json) != bool(local_archive) or (as_of and not release_json):
        raise ValueError('offline replay requires release metadata and matching archive')
    output.mkdir(parents=True, exist_ok=False)
    reports = output/'reports'
    reports.mkdir()
    summary = dict(status='blocked', stage='reference', publicationAuthorized=False,
                   independentVerification='pending', persistentState=False,
                   baselineKind='pinned reconstructed reference, not last-known-good',
                   userCheck='not supplied; browser storage not accessed', mode='offline' if release_json else 'live')
    try:
        cache = output/'cache'
        baseline = output/'baseline.json'
        if baseline_raw is None:
            summary['seedResult'] = make_baseline(baseline, cache, seed_archive)
        else:
            if seed_archive is not None:
                raise ValueError('cannot combine stored baseline and seed archive')
            baseline.write_bytes(baseline_raw)
            summary.update(seedResult='STORED', baselineKind='last stored DRAFT')
        original = digest(baseline.read_bytes())
        summary.update(seedSha256=original, seedSportsSha256=sports_digest(json.loads(baseline.read_bytes())), stage='prepare')
        report = prepare(baseline, reports/'update', cache, release_json=release_json,
                         local_archive=local_archive, as_of=as_of)
        summary.update(release=report['release']['tag'], audit=report['audit'], changes=report['changes'], stage='activation rehearsal')
        managed = Managed(output/'disposable-managed')
        managed.initialize(baseline)
        result = managed.activate(reports/'update')
        if result['status'] not in ('no_change', 'committed') or result['publicationAuthorized'] is not False:
            raise ValueError('unexpected activation rehearsal result')
        if digest(baseline.read_bytes()) != original:
            raise ValueError('reference bytes changed')
        active_hash = digest(managed.active.read_bytes())
        expected = original if result['status'] == 'no_change' else report['candidateSha256']
        if active_hash != expected:
            raise ValueError('disposable active hash mismatch')
        summary.update(status='draft_ready', stage='complete', rehearsal=result['status'], activeSha256=active_hash,
                       candidateSha256=report['candidateSha256'])
        write_new(reports/'activation.json', result)
    except Exception as exc:
        summary.update(status='blocked', error=str(exc))
        write_new(reports/'cloud-summary.json', summary)
        raise
    write_new(reports/'cloud-summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--seed-archive', help='Optional local copy of the pinned reference archive')
    p.add_argument('--release-json'); p.add_argument('--local-archive'); p.add_argument('--as-of', type=date.fromisoformat)
    a = p.parse_args()
    try:
        result = rehearse(a.output, seed_archive=a.seed_archive, release_json=a.release_json,
                          local_archive=a.local_archive, as_of=a.as_of)
        print('CLOUD DRAFT READY:', result['release'], result['rehearsal'])
        print('DISPOSABLE REHEARSAL ONLY; NO PUBLICATION OR PERSISTENT ACTIVATION AUTHORIZED')
        return 0
    except Exception as exc:
        print('CLOUD DRAFT BLOCKED:', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
