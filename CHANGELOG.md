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

### F1-006.4.1 — hotfix
- Исправлен анонимный вызов API F1DB в GitHub Actions: опциональный встроенный токен, без передачи токена в ZIP-загрузки/редиректы и без расширения прав. При исчерпании лимита обновление по-прежнему блокируется.
- Добавлены 4 теста авторизации и изоляции токена; облачная приёмка ожидается.

## F1-006.5 — persistent DRAFT storage
- F1-006.4.1: облачный hotfix bbe01b5 успешен (2m09s, скриншот пользователя).
- Добавлены отдельная ветка f1-data, явный bootstrap, проверенный манифест, чтение последнего сохранённого DRAFT и CAS-запись через Git с историей.
- Workflow сохраняет спортивные изменения; прежняя база не меняется при no_change или блокировке. Нет публикации Pages. См. docs/F1_006_5.md.

## F1-006.6A
- Exact DRAFT site bundle from persistent f1-data, audited before assembly, byte-identical official.json, allowlisted files and SHA-256 report, explicit blocked publication state.
- Read-only cloud site-rehearsal tied to successful persistence commit/hash and checked-out web assets; temporary review artifact, no Pages deployment.
- Visible F1DB / CC BY 4.0 attribution. 14 new tests; 189 Python / 44 JS passing locally.

## F1-007.1 — redesign shell and calendar
- New responsive navigation, season overview and leaders, event rows, theme styling and round-number chart ticks. No changes to data contracts, forecasting, persistence, or publication gate.
- F1-006.6A cloud run #4 succeeded (6cf183c); F1-007.1 local visual acceptance pending.

## F1-007.2A/B — standings and local media foundations
- Adjacent standings gaps, conservative champion markers, no historical snapshot spoiler.
- Local flag images, exact archive circuit-layout mapping and optional local image bundle; network collection/season-specific logo review pending. No publication or changes to user data.

## F1-007.3
- Карточка гран-при, подиум окончательной классификации, Δ позиций, навигация по этапам, адаптивная схема.
- Без изменений официальной базы, media pack, прогноза, ключа localStorage или публикации.
- 62 JS и 4 целевых Python теста прошли; synthetic Chromium smoke PASS. Реальная визуальная приёмка ожидается.

## F1-007.4
- Графический H2H: карточки пар, независимый счёт по сессиям, накопительная динамика, таблица результатов этапов и навигация.
- Сравнение только final, одна заявка и конструктор, исключение противоречивых и дублирующихся записей. Пропуски не поражения.
- 68 JS, 4 Python preview build, Chromium synthetic/2026 и модель 2000 PASS. Данные, медиа, прогнозы и публикация не изменены.

## F1-007.5 — 2026-11-28
- Аналитический дашборд: диаграммы побед и опубликованных зачётов, форма последних пяти завершённых этапов, полнота данных, строгие final-сессии.
- Сохранены прогнозы, сравнение и шансы на титул. 76 JS, 4 Python preview build, Chromium с реальным импортом 2026 и имитацией fetch/storage.
- F1-009: зафиксирована последующая задача прогнозирования гран-при по характеристикам трасс, пилотов и команд.

## F1-007.6 — 2026-11-28
- Новый локальный sync_media.py, точный архив кандидата, динамическая привязка конфигурации трассы, будущие сезоны, миграция старого пакета и атомарное сохранение с SHA-256 backup.
- Поиск новых фото/схем, кандидатов логотипов без автоматического утверждения; опциональный вызов после успешного prepare_update. Публикация и расписание не включены.
- Зафиксирован F1-010 — детализация побед и навигация назад. F1-009 сохранён без изменений.


## 2026-11-28 — F1-012.2 (кандидат, независимая приёмка ожидается)

Утверждён порядок F1-012 → F1-009 → F1-010 → F1-011 → F1-008. F1-006.6B (контролируемая публикация, rollback, production schedule) остаётся в F1-012.4–6. F1-007.6 сохранён. F1-012.2: единый статический сборщик, локальная сборка и закрытая репетиция /formula1/, контроль входных файлов, перенос прогнозов без перезаписи, DRAFT-манифест. Публичная сборка не разрешена: независимая проверка данных и прав медиа ожидается. Браузерный smoke BLOCKED средой, повторить на ПК владельца. Актуальная рабочая копия: HEAD 6cf183c0fa691885f6946ad69ae46ad27d6e1bd0 с незакоммиченными F1-007.*; патч не применён к ней автоматически. F1-012.3 только по решению архитектора. Сохраняются все предшествующие требования, включая автообнаружение будущих сезонов, прогнозы, детализацию и шины/стратегии.


## F1-012.2.1 — замечания архитектора (кандидат)

R-03: устранена потеря привязки old-race → new-race при повторном импорте одинаковых прогнозов; исходные дата и порядок сохранены, конфликты атомарно блокируются, непривязанные записи сохраняются, импорт исторических данных маркирован без подтверждения своевременности. R-02: обновлён сквозной smoke с независимыми origins, синтетическим непустым прогнозом, фактическими проверками результата, повтором, конфликтом, повреждением, backup, настройками и SHA спортивных данных; оба loopback перехода BLOCKED политикой среды. 105 Python / 85 JS PASS, реальные локальная и Pages-репетиция совпадают по девяти файлам. Синтетическим является только медиапакет; DRAFT и workflow artifact не гарантируют приватность. F1-012.3: проверка видимости существующих артефактов и безопасное облачное хранение реального медиа. F1-012.4–6: F1-006.6B, разрешение публикации, rollback, расписание. F1-008 — после F1-009/010/011. Накопительный патч от исходных 176 файлов, прежний патч не устанавливать. Приёмка архитектора и браузерный прогон на ПК ожидаются; никаких Git push, публичной публикации или настроек не менялось.

## F1-012.3 — 2026-11-28 (кандидат, не релиз)

- F1-012.2/2.1 приняты архитектором: 105 Python/85 JS/50 browser PASS. Зафиксирована правка smoke `.gp-sessions [data-kind="prediction"]` и ожидаемый SHA-256 `a19790c9766c2e8b004c553d331a7574c5c4e1104c8f1a7fe264f69d741a9b49`; фактический хеш ПК проверить.
- Read-only аудит public GitHub: f1-data неизменен, 8 доступных ZIP, 12 деревьев истории, Pages уже имеет исторические runs. Полные настройки/история/локальный HEAD pending.
- Новый локальный media catalog, rights register, release manifest/store, rollback, security audit, read-only manual CI и lock версий зависимостей; исходный UI, старый сборщик и данные не изменены. 136 Python/85 JS, две реальные DRAFT-сборки и локальное восстановление PASS. Права media/flags и облачное хранение BLOCKED.
- Удалённых изменений нет. F1-012.4 не начат. F1-008 переносится в конец после F1-009/010/011; F1-006.6B в F1-012.4–6.

## Контрольная точка 2026-11-28 — F1-012.4 (подготовка; не публикация)

- F1-012.3 локально принят владельцем: PREFLIGHT_OK (78 reference paths; 14 changes), APPLY_OK; worktree 197 файлов, findings отсутствуют; история 12 commits / 164 blobs, замечаний нет. R01 принят: 2 файла, 7/7 тестов, индекс 117 файлов, findings=[] и blocked=[]. Источник — протокол владельца; не повторное удалённое испытание.
- F1-012.2.1 принята ранее (105 Python, 85 JS, 50/50 браузерных). Коррекция селектора `.gp-sessions [data-kind="prediction"]` сохранена; новый smoke расширен режимом circuits-only.
- F1-012.4: кандидат ограниченного профиля (61 SVG, 526 привязок, 475 кодов стран); оригинальные 132 фото, 286 командных визуалов и 42 флага не удаляются, но до проверки не отправляются в публичный Git. Полный локальный режим сохранён. Данные DRAFT остаются без разрешения публикации; реестр кандидата не является авторизацией.
- Подготовлены отдельный workflow_dispatch Pages, внешняя SHA-256 привязка одобрения, отдельный проверенный снимок данных (предложенная f1-approved-data), неизменяемые версии и локальный rollback. f1-data по-прежнему двухфайловая; новых удалённых веток нет. Только после независимого GO и согласования переключения Pages допустим запуск.
- GitHub: публичный; Pages main/root HTTPS по сведениям владельца. На скриншоте выбрано Require approval for all external contributors, сохранение не подтверждено. Фактическая рабочая копия после R01 недоступна: применимость проверяется по эталонным SHA-256 перед любыми изменениями.
- Открыто: независимая проверка конкретных спортивных данных; согласование сокращённого профиля и атрибуции; безопасный публичный source mirror; CI/зависимости в целевом окружении; повторный browser smoke (в среде исполнителя loopback блокируется); резерв текущего сайта; разрешение на настройки, push, merge, публикацию. F1-012.4 остаётся на рассмотрении, F1-012.5 не начат.
- Порядок не изменён: F1-012.4 → F1-012.5–6 → F1-009 → F1-010 → F1-011.1–4 → F1-008. Автоматическое обнаружение будущих сезонов без ежегодной ручной правки остаётся обязательным.
