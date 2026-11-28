# F1-007.2.4 — historical logo collection, batch 02

Local DRAFT only. User's previous run confirmed 132 portraits, 61 circuit layouts and 7 team-season logos. This patch adds a catalog of 30 additional Commons files mapped to 64 distinct constructor-season keys. It does not contain image bytes, change the downloader, change official results, or authorize public deployment.

## Run (Windows PowerShell, project root)

```powershell
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --approved-logos references/f1-logo-reviewed-batch-02.json --retry-missing
```

Expected maximum after successful downloads: 132 photos, 71 logos (team-season records), 61 circuits. Existing entries are skipped by the installed loader. Preserve private/media-2000-2026. A missing logo must not affect the sports data or replace an existing logo. Inspect missing.logos, errors and coverageMissing.teamSeasons in media-report.json. Do not re-run the broad candidate discovery merely to apply this catalog.

## Review criteria

The Commons file pages were inspected for team identity, description/date and provenance. The year assignments are representative season-level emblems for local visual review; they are not guaranteed to capture every race-specific sponsor change. Some files are third-party reconstructions or photographs, not original vector graphics. McLaren marque periods and Toyota title identity are supported by official team/manufacturer history; other ranges can reflect generic team identity across short-lived constructors. The exact logos, date ranges and legal rights still require final visual/provenance review before public deployment. Runtime license checks remain unchanged. Commons metadata alone does not establish trademark permission or that the uploader owns all underlying rights. No public deployment is authorized. The report counts coverage only if the requested files successfully download; it is not a claim of actual installed coverage.

## Verification

Catalog generation verified all 64 new keys against the supplied 41-team season catalog (286 total keys), no duplicates or overlap with batch 01. Existing 25 loader unit tests passed locally; live network downloads and image appearance are not tested by this patch. See reports/f1007-2-4-logo-coverage.json for remaining years. Current scope is seasons 2000–2026. No automatic extrapolation of a logo into future seasons.
