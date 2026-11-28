# F1-007.2.3 — точечное восстановление фотографий и первая подборка логотипов

Исходный отчёт пользователя: 128/132 фото, 61/61 трасс, 0 логотипов; 297 кандидатов для 40/41 команд. Из 286 пар команда–сезон семь вынесены в первую подборку, только для локального просмотра. Остальные не утверждены. Фильтр очереди исключает очевидно посторонние названия, но не является проверкой исторического периода или лицензии.

## Фотографии

В `collect_media.py` добавлены четыре точно сопоставленных по идентификатору F1DB и дате рождения кандидата. Принимается только совпадающее каноническое имя файла и разрешённая лицензия из ответа API; автор указан по странице Commons, а не по имени загрузившего. Обычный алгоритм остаётся резервным.

- Cristiano da Matta: https://commons.wikimedia.org/wiki/File:Cdmlb06.jpg — CC BY 2.5, DECHUSA Motorsport Photography+ / www.dechusa.tk.
- Juan Pablo Montoya: https://commons.wikimedia.org/wiki/File:J_p_montoya.jpg — CC BY-SA 3.0, Rick Dikeman.
- Patrick Friesacher: https://commons.wikimedia.org/wiki/File:Patrick_Friesacher.jpg — CC BY-SA 2.0, Dan Smith.
- Sergey Sirotkin: https://commons.wikimedia.org/wiki/File:Sergey_Sirotkin_SMP_Racing.jpg — CC0, SMP Racing.

## Логотипы

`references/f1-logo-reviewed-batch-01.json` — первая подборка точных файлов и годов; ссылки на описания включены. API всё ещё проверяет лицензию и формат. `references/f1-logo-review-queue.json` — отфильтрованная очередь из присланного каталога, не разрешение на загрузку. В ней могут оставаться неверные совпадения. Не передавать её в --approved-logos. Торговые марки и условия использования при публичной публикации требуют отдельной проверки. Загрузка не означает разрешение на публикацию. Для одной группы годов изображение запрашивается один раз. Временная ошибка cirrussearch-too-busy-error теперь повторяется.

## Локальная проверка (PowerShell из корня проекта)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_collect_media.py -v
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --photos --retry-missing --driver f1db:cristiano-da-matta --driver f1db:juan-pablo-montoya --driver f1db:patrick-friesacher --driver f1db:sergey-sirotkin
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --approved-logos references/f1-logo-reviewed-batch-01.json --retry-missing
```

25 целевых тестов пройдены. Полный регрессионный набор и сетевой прогон не выполнены. DNS commons.wikimedia.org в среде разработки не разрешается. Исходный каталог и официальная база не изменяются; изменения в пользовательской рабочей копии происходят только при локальном запуске. Перед публикацией проверить авторство и условия лицензий всех изображений, а также исторические варианты логотипов.
