# F1-002 — pilot season 2000 reconciliation

Date: 2026-11-26. Base: v0.1.0 plus F1-002 importer and standings patches. No schema version change: `adjustments` already exists in the accepted contract.

## Findings

- 17 completed races, 373 race result rows, 23 drivers, 11 constructors, 17 circuits; no duplicate participants in a session. Winner, winner lap count, race date and winner elapsed time independently matched for all 17 rounds against https://www.formula1.com/en/results/2000/races.
- Final driver points and positions compared with Formula1.com (all 23); seven missing zero-point positions filled from the published table, not from row order. Nine published constructors compared; Minardi and Prost retained as unlisted zero-point participants.
- McLaren raw driver/race point total and Jolpica snapshot = 162, independent official constructor total = 152. Official team event table reports 6 rather than 16 points for Austria. The constructors-only deduction of 10 points was reported 25 July 2000 (see reference source list).
- 4/17 qualifying sessions have 22 entries each, 13 missing (rounds 2, 5–15 and 17). All four available pole winners and times match the published pole table. Missing sessions are labelled `unavailable` with an existing source ID for the recorded query. No qualification is fabricated from grid positions. Patched importer now retains explicit unavailable sessions for completed races with empty qualifying responses.
- 11 race rows have a classified result with status `unknown` (e.g. technical failure/collision), 16 retired rows have unknown start status, two DSQ rows show positive laps but started=null; 3 withdrawals have unknown start status. Status normalization needs separate review; not corrected silently. No fastest-lap or stint records in candidate.

## ADR proposal: raw snapshot and reconciled snapshot

Keep `private/candidate-2000.json` and raw cache unchanged. `review_2000.py` creates a new draft candidate only. The reconciled standings are authoritative as of the snapshot and include the verified correction; **never add `adjustments` to those snapshot totals again**. For a derived historical series starting from race points, apply the one constructors-only delta once from `afterRound=10` in retrospective charts. A contemporaneous decision timeline would require a separate date-aware contract. The adjustment has two source references (official team stage-by-stage points and contemporary reporting). Existing `sourceIds` retained; external reference sources added. Sources consulted as web pages have sha256=null; original API source digests were not reverified against raw bodies in this audit. `datasetStatus` remains `draft`.

The tool rejects unexpected point/position differences, incorrect winner dates/laps/times, duplicate/unknown adjustments, a different participant set and non-draft datasets. The scope is season 2000 only; reference row counts are pilot assertions and not general racing rules. It does not independently compare every result row with Formula1.com, classify all retirements, or fill missing qualifying rows. The final snapshot is not a production release.

## Windows commands (offline)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/review_2000.py private/candidate-2000.json --output private/candidate-2000-reviewed.json --report private/review-2000-report.json
.\.venv\Scripts\python.exe tools/validate_data.py private/candidate-2000-reviewed.json
```

Expected 39 tests with candidate and legacy backup present; five pilot-data tests skip if candidate is absent. Output/report must not exist yet. Do not delete the raw candidate or cache. Use a different new output name for another run. Candidate remains private and must not be uploaded. Review package does not change `schemas/` or promote a dataset. Next: independently recover missing qualifying data, audit statuses and row-level results, then extend reconciliation to 2007/2021/2026.
