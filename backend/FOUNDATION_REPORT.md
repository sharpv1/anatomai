# MEDEXA Backend 2.0 — отчёт этапа 1

Дата: 20 ноября 2026. Ветка: `feature/medexa-backend-foundation`.
Основа: `release/anatomai-1.0`, `b3576d515aa39923daec20e0e420456c8bf96e7e`.

## Состав изменений

- `docs/MEDEXA_BACKEND_ARCHITECTURE.md` перенесён без изменений из
  `docs/medexa-backend-architecture` (`8a7be6a`); другие коммиты не cherry-pick.
- `backend/pyproject.toml`, `.python-version`, `uv.lock`: Python 3.12,
  зафиксированные runtime/dev зависимости, Ruff, mypy, Pytest.
- `backend/app/main.py`, `api/health.py`: app factory, lifecycle/dispose,
  `/live`, `/ready`, metadata и OpenAPI error envelope.
- `backend/app/core/`: environment settings/SecretStr, безопасное построение DSN,
  JSON logging, request context, единые ошибки, транзакционная идемпотентность.
- `backend/app/db/`: SQLAlchemy async engine/session factory, bounded pool,
  schema gate, metadata/model `idempotency_requests` с UNIQUE/CHECK/index.
- `backend/alembic.ini`, `migrations/`: явная начальная миграция,
  транзакционный advisory lock, offline/online режимы, без startup create_all.
- `backend/Dockerfile`, `compose.dev.yaml`, `compose.test.yaml`: изолированные
  development/test проекты, non-root API/check, loopback-only API, private DB,
  tmpfs test data, project-scoped network/volume без external ресурсов.
- `backend/tests/`, `scripts/check.sh`: unit, PostgreSQL integration, миграции,
  concurrency/rollback/TTL, проверки ошибок, схемы и ограничений БД.
- `.github/workflows/medexa-backend.yml`: read-only workflow, Python 3.12,
  PostgreSQL 16 service, locked dependencies, lint/types/tests/Compose validation
  и сборка runtime image, без deploy/merge и production credentials.
- `backend/README.md`, `.env.example`, `.gitignore`, `.dockerignore`: запуск,
  конфигурация, ограничения, локальные секреты и безопасный откат.

Frontend (`src`, `public`, root package/lock, Vite/TS config, существующие tests)
не изменялся. Старый Backend, Nginx, Preview/Production и действующие базы не
подключались. Добавленный Compose не является изменением действующей инфраструктуры.

## Результаты проверок

| Проверка | Результат |
|---|---|
| Python unit + integration | **38 passed**, без skipped, в test Compose с PostgreSQL **16.16** и Python **3.12.16** |
| Ruff lint | PASS: `ruff check app migrations tests` |
| Ruff format | PASS: все 23 Python-файла соответствуют format |
| mypy strict | PASS: 15 app source files |
| uv lock | PASS: lock согласован с pyproject, 38 packages в resolution включая проект |
| Миграции на PG16 | PASS: upgrade → downgrade base → upgrade → повторный upgrade; один head `0001_foundation`; `alembic check` без drift |
| Идемпотентность | PASS: replay, изменённый body, отдельные actor/operation scopes, concurrent same-key с одним callback, общий rollback domain write/record, TTL, обязательная транзакция |
| Ограничения PostgreSQL | PASS: completed без status, с status=500 или JSON-array вместо object отвергаются CHECK |
| HTTP/errors | PASS: liveness без БД; readiness timeout/failure; 404/405/409/422/500; request ID; concurrency context; OpenAPI совпадает с envelope |
| Compose dev/test config | PASS: `docker compose ... config --quiet` |
| Docker builds | PASS: runtime и test targets, locked install, UID 10001 runtime |
| API до миграции | PASS: `/live` 200, `/ready` 503; никаких auto migrations |
| API после миграции | PASS: `/ready` 200, 20 последовательных readiness-запросов |
| БД остановлена/восстановлена | PASS: `/live` 200, `/ready` 503; после восстановления `/ready` 200 без перезапуска API |
| Логи API | PASS: 75 записей разбираются как JSON, содержат event/timestamp; реальный одноразовый DB password в логах отсутствует |

Интеграционные проверки выполнены внутри отдельной сети test Compose с ephemeral
БД. Прямое подключение из host Python к internal Docker bridge в этой среде
недоступно; это не использовалось как основание пропустить PG-тесты. HTTP smoke
выполнялся через loopback **внутри API-контейнера**, с настоящим соседним PG16.
Доступ из браузера к host port в этой среде не проверялся.

GitHub Actions добавлен для повторения проверок на отдельном runner. Фактический
статус конкретного запуска следует смотреть в GitHub Checks PR; данный отчёт
фиксирует локальные проверки, а не заранее объявляет удалённый CI успешным.
Frontend TypeScript/build/unit не перезапускались: Frontend не менялся.

## Базовое потребление памяти

Среда: nested Docker 29.9.2, Debian 13 x86_64, VFS, 3 CPU, Docker-visible RAM
около 9.7 GiB. Это **не целевой VPS Ubuntu 24.04 / 1 CPU / 2 GB**.
API — один worker; PostgreSQL — shared_buffers=128 MB, max_connections=25.
Замер после миграции и 20 readiness-запросов, без банка вопросов и бизнес-нагрузки.

Конфигурация Compose задаёт API 384 MiB / 0.5 CPU и PostgreSQL 512 MiB / 0.5 CPU;
HostConfig подтверждает эти значения. Но `docker stats` возвращает обоим контейнерам
одинаковое значение около 1.85 GiB / 8 GiB. Поэтому изолированное cgroup-потребление
и **фактическое соблюдение лимитов в этом nested runtime не подтверждены**.
Нельзя приписывать эти 1.85 GiB одному API или суммировать счётчики.

Дополнительно считан `/proc/<pid>/smaps_rollup` внутри соответствующих PID namespace:

| Группа процессов | PSS | Метод |
|---|---|---|
| Uvicorn + docker-init | 80 544 KiB ≈ **78.66 MiB** | Сумма Pss двух процессов, без процесса измерения |
| PostgreSQL | 33 625 KiB ≈ **32.84 MiB** | Сумма Pss postmaster/children/соединения, shared pages учитываются пропорционально |
| Сумма групп | ≈ **111.49 MiB** | Ориентир process memory, не total container working set |

PSS не включает весь page cache, kernel/network, Docker daemon, host OS, backup и
будущие worker/import. Нельзя считать это доказательством вместимости VPS.
**Надёжный контейнерный RAM benchmark и нагрузочный тест на целевом VPS не
проводились**; перед будущим развёртыванием нужны отдельные измерения с рабочими
cgroup, реалистичным банком и concurrency.

## Особенности тестовой среды

- TLS proxy потребовал доверенный CA через необязательный BuildKit `package_ca`.
  Проверка TLS не отключалась; CA передавался временным secret, не сохранён в Git
  или финальном image layer. README описывает этот opt-in механизм.
- VFS хранит полные копии слоёв: первоначальные сборки исчерпали 8 GB диска.
  Dockerfile уменьшен по числу слоёв; удалены только созданные этой задачей
  контейнеры/устаревшие image/cache records. После этого окончательная test-сборка
  и все 38 тестов завершились успешно.
- Test и smoke проекты остановлены, их контейнеры/сети удалены; временный пустой
  smoke dev volume удалён явно. Другие проекты/volumes не очищались.

## Граница готовности и откат

Этап 1 готов к ревью, **не к production**. Нет Telegram auth/session/RBAC, content
модуля, попыток, платежей, worker/outbox, rate limits, TLS/Nginx или offsite backup.
Идемпотентность пока внутренняя; actor_id станет FK users на этапе identity,
чтобы не создавать фиктивную пользовательскую модель раньше времени.

Dev DB owner упрощает локальные миграции и не является production DB-role.
Docker tags требуют закрепления digest при подготовке production. Измеренные
PSS не снимают необходимость нагрузочного и эксплуатационного gate архитектуры.

Откат: закрыть PR или revert foundation commit; остановить только его Compose
project. Для production восстановление/миграции здесь не предусмотрены и не
выполнялись. Main, Preview, Production, VPS и существующие БД не менялись.
