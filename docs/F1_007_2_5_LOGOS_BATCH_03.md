# F1-007.2.5 — historical logo candidates, batch 03

Local DRAFT only. The user confirmed 132 portraits, 61 circuit layouts and 71 existing team-season logo records. This catalog contains 19 additional Commons files covering 41 new team-season keys. If all download successfully, coverage reaches 112 of 286 keys (30 of 41 constructors represented in at least one season). Previous records must be preserved.

```powershell
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --approved-logos references/f1-logo-reviewed-batch-03.json --retry-missing
```

Check media-report.json: present, errors, missing.logos and coverageMissing.teamSeasons. The latter is the outstanding season-level list. Do not remove existing private media. No changes to downloader, sports database or publishing workflow. This catalog is not an image archive.

Commons descriptions and source links were inspected. Some entries represent a generic constructor identity for a provisional range rather than a certified season-specific sponsorship variant (Arrows, Minardi, Prost, Honda, Force India and Haas). Several are photographs, not clean vector marks (Ferrari, Marussia, McLaren 2000 and Team Lotus 2011). Check appearance and source rights before public use; Commons tags do not establish all underlying rights. The low-resolution Mini Free Logo series and incorrectly identified Minardi belts logo were excluded. Ferrari file named Mexican Grand Prix 25 is dated 2015 in its description; it is not a 2025 logo. No assumption that any emblem carries into future seasons.

Verification: all requested keys are present in the supplied constructor-season inventory; zero duplicate keys and zero overlaps with batches 01 and 02. 25 existing downloader unit tests passed. No live image download or visual review of the installed files was performed here. See coverage report for remaining keys. Publication remains blocked.
