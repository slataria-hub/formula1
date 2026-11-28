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

## F1-005 championship probabilities
The local preview includes a read-only Monte Carlo estimate for the Drivers' and Constructors' titles. It uses season-specific scoring profiles, current published standings, remaining race/sprint sessions, and an exact mathematical clinch check. See `docs/F1_005.md` for methodology, limits, FIA sources and local commands. No forecast authorizes publication of a draft dataset.

### Cloud DRAFT rehearsal (F1-006.4)
See [F1-006.4](docs/F1_006_4.md). Branch pushes can run the read-only GitHub Actions rehearsal. It rebuilds an initial reference, checks latest F1DB, and uploads DRAFT diagnostic artifacts only. Schedule/manual dispatch require the workflow on the default branch; no merge, publication or persistent cloud activation is authorized yet.

F1-006.5: постоянное DRAFT-хранилище `f1-data` (явный bootstrap, история Git,
без публикации сайта) — [инструкция](docs/F1_006_5.md).

F1-006.6A: `python tools/prepare_publication.py build --output private/publication-local-001` assembles a DRAFT review site from the persistent remote f1-data; `python tools/prepare_publication.py verify --bundle private/publication-local-001` checks integrity. No publication authorization or deployment. See `docs/F1_006_6A.md`.


## 2026-11-28 — F1-012.2 (кандидат, независимая приёмка ожидается)

Утверждён порядок F1-012 → F1-009 → F1-010 → F1-011 → F1-008. F1-006.6B (контролируемая публикация, rollback, production schedule) остаётся в F1-012.4–6. F1-007.6 сохранён. F1-012.2: единый статический сборщик, локальная сборка и закрытая репетиция /formula1/, контроль входных файлов, перенос прогнозов без перезаписи, DRAFT-манифест. Публичная сборка не разрешена: независимая проверка данных и прав медиа ожидается. Браузерный smoke BLOCKED средой, повторить на ПК владельца. Актуальная рабочая копия: HEAD 6cf183c0fa691885f6946ad69ae46ad27d6e1bd0 с незакоммиченными F1-007.*; патч не применён к ней автоматически. F1-012.3 только по решению архитектора. Сохраняются все предшествующие требования, включая автообнаружение будущих сезонов, прогнозы, детализацию и шины/стратегии.


## F1-012.2.1 — замечания архитектора (кандидат)

R-03: устранена потеря привязки old-race → new-race при повторном импорте одинаковых прогнозов; исходные дата и порядок сохранены, конфликты атомарно блокируются, непривязанные записи сохраняются, импорт исторических данных маркирован без подтверждения своевременности. R-02: обновлён сквозной smoke с независимыми origins, синтетическим непустым прогнозом, фактическими проверками результата, повтором, конфликтом, повреждением, backup, настройками и SHA спортивных данных; оба loopback перехода BLOCKED политикой среды. 105 Python / 85 JS PASS, реальные локальная и Pages-репетиция совпадают по девяти файлам. Синтетическим является только медиапакет; DRAFT и workflow artifact не гарантируют приватность. F1-012.3: проверка видимости существующих артефактов и безопасное облачное хранение реального медиа. F1-012.4–6: F1-006.6B, разрешение публикации, rollback, расписание. F1-008 — после F1-009/010/011. Накопительный патч от исходных 176 файлов, прежний патч не устанавливать. Приёмка архитектора и браузерный прогон на ПК ожидаются; никаких Git push, публичной публикации или настроек не менялось.
