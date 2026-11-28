# F1-007.2.2 — совместимость с адресами миниатюр Wikimedia

Локальный отчёт: 2/132 фото, 61/61 трасс. Для Antonelli, Hamilton, Verstappen поиск нашёл подходящие файлы, но `unexpected_image_or_source_host` блокировал их. Реальные ответы API Commons могут содержать `thumb.wikimedia.org` и `commons.wikimedia.org/wiki/Special:FilePath/` вместо прежнего `upload.wikimedia.org` (см. https://www.mediawiki.org/wiki/API:Imageinfo и https://commons.wikimedia.org/wiki/User:Sciking/UploadWorkbench/Metadata.json).

Изменения: HTTPS, точный список доменов, проверка пути для Commons, проверка каждого перенаправления и конечного адреса, стандартная ширина 320, резервная попытка оригинального изображения в пределах 700000 байт, каноническая ссылка на страницу файла, вывод imageHost и причин отказа. Проверки даты рождения, лицензии и автора сохранены. OGL 3 пока не поддерживается. Не меняются официальный JSON, схемы, прогнозы, интерфейс и публичный сайт. Существующий visual-media.json сохраняется, успешные элементы пропускаются. Не запускать два сборщика одновременно.

21 целевой Python-тест прошёл, 7 новых. Полный набор и реальные сетевые скачивания не проверены: DNS недоступен в среде разработчика. Тестовые HTTP-ответы имитированы.

## Windows

Остановить старый сборщик через Ctrl+C. Распаковать с заменой файлов, не удаляя private/media-2000-2026.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_collect_media.py -v
.\.venv\Scripts\python.exe tools/collect_media.py --baseline private/managed-preview/site/official.json --archive private/f1db/f1db-csv.zip --output private/media-2000-2026 --photos --retry-missing --driver f1db:lewis-hamilton --driver f1db:max-verstappen --driver f1db:kimi-antonelli
$r = Get-Content private/media-2000-2026/media-report.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.present
$r.photoDiagnostics.'f1db:lewis-hamilton' | ConvertTo-Json -Depth 10
$r.photoDiagnostics.'f1db:max-verstappen' | ConvertTo-Json -Depth 10
$r.photoDiagnostics.'f1db:kimi-antonelli' | ConvertTo-Json -Depth 10
$r.errors
```

Не запускать массовую загрузку, пока контрольная попытка не подтверждена. При успешном скачивании трёх фото итог должен быть 5 или больше, если предыдущий запуск успел скачать другие фото. Для логотипов всё ещё требуется историческое и лицензионное подтверждение.
