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
