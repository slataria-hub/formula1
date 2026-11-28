# F1-007.2.6 — fourth local draft logo batch

Based on user's confirmed 111 stored team-season entries after batch 03 (only McLaren 2015 failed). Batch 04 contains 21 image selections covering 33 currently missing entries, including alternative McLaren Honda image. Potential total 144/286, 142 still missing. Seven entries have dated source support; the others are provisional representative team identities, not verified exact season or sponsor variants. Local review only, not a publication approval. Underlying trademarks and copyright, and visual match, require separate review. Existing downloaded entries are not overwritten. No images are included; network fetch is not tested here.

The loader now records `logoDiagnostics` for attempted team-season keys, including license/author, unsupported media and host failures. This does not relax existing checks. Prior photo and logo assets remain intact. The target catalog comes from the previously uploaded logo-candidates(1).json and three prior batch manifests. Overlap is allowed only with the previously failed McLaren 2015, which is absent from the confirmed set.

PowerShell from repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_collect_media.py -v
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --approved-logos references/f1-logo-reviewed-batch-04.json --retry-missing
$r = Get-Content private/media-2000-2026/media-report.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.present
$r.errors
$r.missing.logos
$r.logoDiagnostics.'f1db:mclaren@2015'
```

Full regression suite and remote network not run. Target loader tests: 26 passed, including new test for shared diagnostics across two seasons.
