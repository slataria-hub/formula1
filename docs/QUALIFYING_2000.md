# F1-002 — qualifying recovery pilot (season 2000 only)

Run from repository root, after review_2000.py has completed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/import_qualifying_2000.py private/candidate-2000-reviewed.json --output private/candidate-2000-qualified.json --report private/qualifying-2000-report.json
.\.venv\Scripts\python.exe tools/validate_data.py private/candidate-2000-qualified.json
```

Expected 46 tests with the original candidate and backup present. Seven new tests use synthetic HTML built from the pilot candidate's IDs and reference pole times, not actual downloaded pages. The live HTML parser/HTTP path has NOT been verified against raw Formula1.com HTML because DNS failed in the development environment. The source tables inspected in the browser archive show a single qualifying time and lap count, e.g. Brazil and Europe. The pilot expects 285 added results (12×22 plus 21), 373 total, and 17 sessions. If the source differs, it fails closed; expected counts are specific to season 2000, not general F1 rules. Do not treat a failed check as permission to force the input to match.

- The input file must already be reconciled. Original race rows, standings, McLaren adjustment and four existing qualifying sessions stay unchanged. Output is always draft.
- Uses complete normalized driver names (never surname only), historical team aliases, calendar dates, session headings, distinct positions/participants, pole and lap time, and race entrant-set comparison as a season-specific cross-check. Real qualifying entrants can differ from race entrants in other seasons; do not generalize this constraint. Such a discrepancy needs independent review.
- Single-session time stored at qualifyingTimesMs[0]; the other two fields are null, NOT modern Q1/Q2/Q3 segments. No synthetic times in production.
- Caches successfully parsed HTML and metadata in private/formula1-html-2000; hash is of actual HTML bytes. `retrievedAt` records when bytes were ingested; for manually saved HTML this is not proof of original publication/download time. Re-running with the same input and new output paths reuses the cache. `--offline` requires cached HTML or `--html-dir`.
- If the site blocks automated access, do not bypass its restrictions. Where permitted, manually save the official page HTML (not a screenshot) into private/formula1-manual-2000/round-NN.html and use `--html-dir private/formula1-manual-2000`. Existing cache takes precedence. Keep raw pages and derived candidate private; check source terms and redistribution rights before publishing historical data. No live credentials are required.
- The four existing qualifying sessions are not independently compared row by row in this patch. Race classification row-by-row checks and publication rights remain open; no verified dataset or GitHub Pages deployment.

Missing-round URLs:

- round-02.html: https://www.formula1.com/en/results/2000/races/48/brazil/qualifying/0
- round-05.html: https://www.formula1.com/en/results/2000/races/51/spain/qualifying/0
- round-06.html: https://www.formula1.com/en/results/2000/races/52/europe/qualifying/0
- round-07.html: https://www.formula1.com/en/results/2000/races/53/monaco/qualifying/0
- round-08.html: https://www.formula1.com/en/results/2000/races/54/canada/qualifying/0
- round-09.html: https://www.formula1.com/en/results/2000/races/55/france/qualifying/0
- round-10.html: https://www.formula1.com/en/results/2000/races/56/austria/qualifying/0
- round-11.html: https://www.formula1.com/en/results/2000/races/57/germany/qualifying/0
- round-12.html: https://www.formula1.com/en/results/2000/races/58/hungary/qualifying/0
- round-13.html: https://www.formula1.com/en/results/2000/races/59/belgium/qualifying/0
- round-14.html: https://www.formula1.com/en/results/2000/races/60/italy/qualifying/0
- round-15.html: https://www.formula1.com/en/results/2000/races/61/united-states/qualifying/0
- round-17.html: https://www.formula1.com/en/results/2000/races/63/malaysia/qualifying/0
