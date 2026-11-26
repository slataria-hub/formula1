# F1 Grand Prix Analytics 2.0 — Foundation 0.1.0

Дата: 2026-11-26. Задача F1-001, подэтапы 01.1 и 01.2.

Это фундамент новой версии, а не готовый сайт. Рабочая историческая база и интерфейс пока не мигрированы. Примеры в examples/ синтетические; запрещено публиковать их в качестве реальных результатов.

## Начало работы (Windows PowerShell)

Распакуйте F1_REPOSITORY_0.1.0.zip в новую локальную папку. Создайте пустой GitHub-репозиторий (без README, .gitignore и лицензии, чтобы первый push не конфликтовал). В PowerShell откройте эту папку.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/validate_data.py examples/synthetic-dataset.json --user examples/user.example.json
```

Для публикации кода:

```powershell
git init -b main
git add .
git status --short
git commit -m "chore: establish F1 data foundation 0.1.0"
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Замените USERNAME/REPOSITORY реальными именами. Если репозиторий уже содержит коммиты, сначала клонируйте его и распакуйте комплект в клон, вместо git init и remote add. Лицензию выбирает владелец. Публикацию GitHub Pages отложите до готовности нового интерфейса.

## Резервная копия — отдельно

F1_BACKUP_2026-11-26.zip храните локально, не публикуйте. Внутри оригинальные legacy/index23.html, legacy/data.json, контрольные суммы и private/legacy-user-data.json. Можно распаковать в корень локального проекта: .gitignore исключает обе папки. Для проверки: `.\.venv\Scripts\python.exe tools/validate_data.py --backup`. Без локальной копии тест резервного копирования пропускается. Не запускайте старый HTML под адресом нового приложения: его boot() автоматически выполняет дедупликацию, пересобирает периоды и сохраняет localStorage.

## Документация

- docs/DATA_MODEL.md — модель данных, контракт импорта и миграции.
- docs/DECISIONS.md — архитектурные решения.
- CURRENT.md — статус и блокеры.
- TASKS.md — план и критерии приёмки.
- CHANGELOG.md — история версии.
- reports/legacy-audit.json — измерения и перечень дублирующихся идентификаторов.
- reports/test-results.txt — фактический локальный запуск тестов.

## Ограничения

Валидатор проверяет структуру и часть семантических инвариантов, но не подтверждает фактическую достоверность гонок, полноту календаря, соответствие регламентам или зачётам FIA. `--release` — предварительный технический барьер, не сертификат качества. Сетевой импорт и новый UI будут разработаны отдельно. Не изменяйте исходные копии.
