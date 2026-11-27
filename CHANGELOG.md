# 0.1.0 — 2026-11-26

- Неизменённые оригиналы и контрольные суммы в отдельном локальном архиве.
- Инвентаризация 526 этапов, отчёт о повторных ID.
- Контракт 2.0.0 для официальных и личных данных.
- Карантин одного существующего прогноза, ноль ручных поправок очков.
- Независимый валидатор и 14 тестов. UI и исторические данные не мигрированы.

## F1-002 — итерация 1 (не релиз)
- Фундамент v0.1.0 принят: пользователь подтвердил 14/14 тестов, main и тег опубликованы.
- Добавлен пробный импортер сезона и девять синтетических тестов. Данные только draft; схема не изменена.
- Реальная загрузка и независимая сверка ещё не выполнены (DNS недоступен в среде разработки).

## F1-002B — 2026-11-26 (draft)
- Пробный Jolpica-импорт 2000, патчи сетевых запросов, поэтапной загрузки, зачётов и независимой сверки; 46 локальных тестов пройдены. Formula1.com HTTP 403.
- F1DB CSV: новый офлайн-импортер, автоматическое обнаружение сезонов, отчёт конфликтов, 13 новых тестов. Полный прогон 59/59; независимая проверка ещё не завершена.
- Зафиксировано требование автоматического обновления будущих сезонов и гран-при на этапе 03.

### F1-003 pilot (unreleased)
- Explicit targeted reconciliation of 2000 standings, 2017 Gasly, 2018 Force India; control checks for 2007/2021, no double deductions.
- Optional entrant and external event identity fields; validation of entrant links.
- Conservative driver crosswalk and update safety gate; no automatic user migration or publication.

### F1-003.2 — championship audit (draft)
- Added read-only per-round championship arithmetic, coverage, wins and tentative countback diagnostics. Added crosswalk report classifier.
- Documented source-embedded 2020 Racing Point deduction; do not apply it again. No dataset or schema edits.
- New-year schedules remain supported without a fixed maximum year. No auto-publication.

## F1-003.3 — 2026-11-26
- Добавлены точечная сверка двух промежуточных зачётов и классификация расхождений статусов.
- По указанию пользователя перенос старого тестового прогноза исключён; добавлена безопасная однократная инициализация пустого пользовательского файла с автоматическим выбором последнего сезона.
- База остаётся draft; автоматическая загрузка последующих сезонов остаётся обязательной задачей.

### F1-004.1 — local v2 preview
- Added read-only local browser preview and guarded private build; retained old stylesheet/navigation concept without modifying original app.
- Calendar-derived season list, session results, authoritative standings and awarded-points matrix, actual entrant-aware race lineups, summary dashboard.
- Four Python and six JS tests; 100 Python tests passed in development; Chromium DOM smoke on real 27-season candidate passed. HTTP navigation verification on user's PC pending.

## F1-004.2 — 2026-11-26
- Расширенный календарь и фильтры; H2H по общим классифицированным сессиям, сезонная статистика пилотов, встроенная иконка вкладки.
- 100 Python / 12 JS тестов; реальный кандидат и Chromium DOM smoke. Локальная приёмка ожидается; публикация draft запрещена.

## F1-004.3 — draft
- Графики опубликованных накопленных очков и позиций; сравнение двух пилотов и выбор этапа, таблица статистики. Пропуски не интерполируются. SVG без зависимостей.
- 18 JS-тестов, регрессионные Python-тесты и DOM smoke на 27 сезонах; локальная приёмка ожидается. Не публиковать draft.

## F1-004.4 — draft
- Локальные прогнозы гонок и настройки в отдельном localStorage, пустая инициализация, до 10 пилотов, оценка по прежней формуле, экспорт, проверка дедлайна и внешнего ID.
- 100 Python / 30 JS тестов, сборка 27 сезонов, DOM smoke с имитацией storage. HTTP-приёмка ожидается. Официальная база, исходный сайт и main не изменяются.

## F1-005 — championship probabilities
- Added season-specific scoring profiles for 2000–2026, including 2014 double points, 2019–24 fastest-lap bonus, 2021/2022+ sprint scoring and 2026 shortened-race tables.
- Added exact maximum-points clinch detection and Monte Carlo Plackett–Luce engine for Drivers' and Constructors' titles.
- Added dashboard view, forecast CLI and historical two-round holdout backtest CLI.
- Forecast is read-only; official and user datasets are not modified. Future scoring profiles beyond 2026 are blocked pending FIA review.
- Added 14 JavaScript tests and 26-season exploratory backtest.

## F1-006.1 (2026-11-27)
- Добавлен `tools/fetch_f1db.py`: latest stable F1DB CSV, SHA-256, размер, ZIP/CRC, локальный кеш по версии и хешу, безопасный отказ, ограниченные повторы сетевых запросов.
- 14 новых тестов, полный регрессионный набор 114 Python / 44 JS без пропусков. Реальный архив проверен офлайн, сетевой тест ожидается (DNS недоступен в среде разработки).
- Автоматический импорт, планировщик и публикация пока не реализованы; база и прогнозы не изменяются.

### F1-006.2 — DRAFT update preparation
- Confirmed live F1DB release download on user's PC; local CACHE replay pending.
- Added private update pipeline with release metadata, historical reconciliation, compatibility check, audit and change reports, optional read-only browser prediction backup check. No activation or publication. No hard-coded terminal season.
- Added 12 target tests; offline real archive replay completed with zero audit issues and three countback review candidates.

## F1-006.3 — local managed DRAFT activation
- F1-006.2 locally accepted (126 tests, live CACHE, no sporting changes, 0 audit issues).
- New private-only activation tool: exact hashes, conservative sporting comparison, repeated validation, immutable-by-convention hash-keyed backups, atomic file switch, lock, journal and explicit rollback. Optional user export checks; no browser writes.
- 20 targeted tests. No source schema, preview assets or public deployment changes; publication remains blocked.

### F1-006.4 — GitHub Actions DRAFT rehearsal
- Cloud bootstrap from checksum-pinned reference archive and sporting fingerprint; fetch latest stable and rehearse activation in disposable storage. No persistent production state or publication.
- Read-only branch-push workflow with future schedule/manual dispatch and 14-day report/candidate artifacts; no main changes.
- Ten targeted cloud orchestration tests; local/hosted acceptance pending.
