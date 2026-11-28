# F1-007.2.1 — локальное восстановление наполнения

Полученный отчёт: 61/61 конфигураций, 2/132 фотографий, 0 логотипов; 14 кандидатов для 10/41 команд. 286 сочетаний команда/сезон требуют покрытия. Тайм-аут TLS у Монтойи подтверждён, остальные причины прежний отчёт не различал.

Изменения: Wikipedia redirects + pageprops + свободное pageimage с проверкой Wikidata P569, все P18, fallback поиска Wikidata, нормализация лицензии по URL Creative Commons, диагностические причины, повтор временных ошибок и maxlag, поиск кандидатов логотипов в Commons. Исторические годы и лицензии логотипов всё ещё требуют отдельного подтверждения. Фото не гарантированно снято в выбранном сезоне. Проверка метаданных не заменяет визуальную приёмку. Схемы и существующий пакет сохраняются; не удалять private/media-2000-2026. Сборщик не меняет official.json, прогнозы, публичный сайт. Не запускать два сборщика одновременно.

## Windows

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_collect_media.py -v
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --photos --retry-missing --driver f1db:lewis-hamilton --driver f1db:max-verstappen --driver f1db:kimi-antonelli
$r = Get-Content private/media-2000-2026/media-report.json -Raw | ConvertFrom-Json
$r.present
$r.photoDiagnostics | ConvertTo-Json -Depth 10
$r.errors
```

Если контрольная загрузка успешна, полный поиск:

```powershell
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --photos --retry-missing --priority-season 2026
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --logo-plan
.\.venv\Scripts\python.exe tools/build_preview.py private/managed-preview/site/official.json --output private/preview-design-002b --media private/media-2000-2026/visual-media.json
```

Перезапустить HTTP-сервер на прежнем порту 8765, указав новый каталог. Для отдельного теста использовать --driver, для ограничения числа проверяемых записей --limit-photos. --retry-missing обязателен для повторной попытки после прежнего отчёта. Не применять --approved-logos к непроверенным кандидатам. Диагностика фото сохраняется в photoDiagnostics, текущие ошибки в errors; при повторном запуске прошлые причины могут сохраняться для не проверенных заново ID.

Проверки: 14 целевых Python-тестов (8 новых), 9 целевых JS-тестов. Реальные сетевые вызовы из среды недоступны (DNS); проверены имитации ответов API, а не полнота загрузки. Полный регрессионный набор в этой поставке не запускался.
