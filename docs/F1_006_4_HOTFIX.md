# F1-006.4.1 — GitHub API authentication

First Actions run (commit 4a803cf, run 46040503840) failed in `Prepare and rehearse DRAFT update`: HTTP 403 rate limit exceeded. The same pipeline passed locally. The exact failed HTTP request is not shown in the screenshot; the latest-release API was called anonymously in the original code.

- Pass the built-in `${{ secrets.GITHUB_TOKEN }}` as `F1DB_GITHUB_TOKEN` only to the cloud rehearsal step. No personal token or new write permission is needed for the first retry.
- Use it only for the exact F1DB latest-release API URL. No Authorization header for ZIP downloads, other URLs or redirects. The token is not printed or persisted by the loader.
- Local execution without the variable remains supported. Rate-limit failures still stop the pipeline instead of pretending the cached release is current. No changes to checksum validation or publication permissions.
- If GitHub returns 403 again, inspect `reports/cloud-summary.json` inside the diagnostic artifact to distinguish stage `reference` (seed download) from `prepare` (release lookup/update); a cross-repository authorization restriction or secondary limit may require a separate remedy.

Run `python -m unittest discover -s tests -p test_fetch_f1db.py -v` (18 tests) and push a new commit to the feature branch. Do not rerun the old commit: it lacks the fix. No change to main or GitHub Pages settings.
