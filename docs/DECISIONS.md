# Архитектурные решения (предложенная базовая версия)

- ADR-001: исходники неизменяемы, локальный архив с SHA-256, исключение из Git по умолчанию.
- ADR-002: стабильные ID и явные aliases; автоматическое объединение по фамилии запрещено.
- ADR-003: исторические конструкторы и принадлежность по сессии; lineage не является официальным конструктором.
- ADR-004: официальные очки и статус из источника; классификация, старт, причина завершения независимы.
- ADR-005: отдельный контракт пользовательских данных, карантин старых прогнозов до проверки ID.
- ADR-006: JSON Schema + независимый валидатор; структурная проверка не равна фактической сверке.
- ADR-007: статический сайт GitHub Pages в перспективе, без обязательного платного сервера; новый UI позже.
- ADR-008: транзакционный импорт, происхождение, ревизии и независимые снимки зачётов.

- ADR-009 (к приёмке F1-002): допустить null в позиции зачёта только с явным специальным обозначением источника (`-`, `E`, `D`); не выдумывать места. Сохранить совместимость чтения прежних записей в новом валидаторе.

- ADR-010 (F1-003 pilot): separate entrant from constructor, optional entrantId in session and constructor-standing rows; explicit season/round intervals. 2018 split is evidence-backed; no general entrant inference yet. New frontend must key constructor standings by entrantId when present.
- ADR-011: preserve internal round IDs for compatibility but record F1DB externalEventId and grandPrixKey; block unsafe identity changes and data loss at update gate; explicit migration before accepting reordered calendars. Auto-update scheduler and publication remain stage 03.
