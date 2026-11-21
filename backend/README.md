# MEDEXA Backend 2.0 — Foundation + Identity + Content

Независимый Backend, этапы 1–3a [архитектуры](../docs/MEDEXA_BACKEND_ARCHITECTURE.md).
Python 3.12, FastAPI, Pydantic Settings 2, SQLAlchemy 2 async/asyncpg, PostgreSQL 16,
Alembic. Существующий Frontend и старые серверы не подключены.

## Что реализовано

- `GET /live`: 200 без обращения к БД. `GET /ready`: 200 только после успешного
  SQL-запроса, проверки PostgreSQL 16 и точного совпадения Alembic head;
  иначе 503 `SERVICE_NOT_READY`, без DSN/исключения в ответе.
- JSON-логи с request ID и шаблоном маршрута, без query/body/headers/tracebacks.
- Единый `error.code/message/details/request_id`, включая 404/405/422/500;
  `X-Request-ID` и `Cache-Control: no-store`.
- Транзакционный PostgreSQL primitive идемпотентности: scope actor/operation/key,
  hash JSON, replay, конфликт payload, TTL, атомарный rollback.
- `0001_foundation` создаёт идемпотентность; `0002_identity` добавляет пользователей,
  роли, сессии, replay-защиту, неизменяемый аудит и FK actor_id → users.
- Telegram HMAC, HttpOnly-сессии, CSRF/Origin, RBAC и операторский bootstrap.
  Контракты, настройки и ограничения: [IDENTITY.md](IDENTITY.md).

Добавлен read-only Content API и `0003_content`; контракт, публикационные инварианты,
quarantine исходного банка и файловая доставка описаны в [CONTENT.md](CONTENT.md).
Десять исходных вопросов только в draft. Нет движка попыток, XP, платежей, worker,
production-конфигурации или интеграции с React.
Авторизация выключена (503), пока не заданы собственные bot token и CSRF key. Идемпотентность — внутренний сервис, публичного HTTP endpoint
с произвольным actor_id нет. `/live` и `/ready` выбраны согласно заданию этапа 1;
в архитектурном реестре использовались более длинные `/health/*`.

## Конфигурация

Все настройки читаются из переменных `MEDEXA_*`; `.env` автоматически приложением
не загружается. Для локальных uv-команд используйте `--env-file .env`.
В Git находится только `.env.example` с placeholder, без действующих секретов.

| Переменная | Назначение |
|---|---|
| `MEDEXA_ENVIRONMENT` | development или test; production намеренно не поддержан |
| `MEDEXA_DB_HOST`, `MEDEXA_DB_PORT` | Явный адрес новой локальной БД |
| `MEDEXA_DB_NAME` | Обязательно начинается с `medexa_foundation_` |
| `MEDEXA_DB_USER`, `MEDEXA_DB_PASSWORD` | Обязательны, пустой пароль/REPLACE_ME запрещены |
| `MEDEXA_DB_POOL_SIZE` | 3 по умолчанию, максимум 5, overflow=0 |
| `MEDEXA_READINESS_TIMEOUT_SECONDS` | 3; общий timeout readiness, включая ожидание pool |
| `MEDEXA_CONTENT_CURSOR_SIGNING_KEY` | Отдельный ≥32 байт ключ курсоров; пустой отключает Content API |
| `MEDEXA_CONTENT_ASSET_DELIVERY_ENABLED` | false; включать только с отдельным internal Nginx location |
| `MEDEXA_LOG_LEVEL` | INFO по умолчанию |
| `MEDEXA_DEV_API_PORT` | Только Compose: loopback port, по умолчанию 18081 |
| `MEDEXA_TEST_DB_PASSWORD` | Только test Compose: одноразовый пароль |
| `MEDEXA_RUN_DB_TESTS=1` | Разрешает интеграционные тесты **только** на выделенной test БД |

URL собирается SQLAlchemy URL.create, специальные символы пароля не требуют
ручного URL-encoding. Не выводите `docker compose config`, `docker inspect` или
environment в публичные логи: там могут быть развёрнутые секреты.

В среде с корпоративным TLS proxy Docker build может потребовать доверенный CA.
Dockerfile поддерживает необязательный BuildKit secret `package_ca`, например
`docker build --secret id=package_ca,src=/path/to/approved-ca-bundle.pem --target runtime .`.
В Compose передайте тот же secret через **локальный неотслеживаемый override**
в `build.secrets` выбранных сервисов. Сертификат не копируется в image layer;
TLS-проверку не отключать. В обычной среде этот secret не нужен.

## Docker: отдельное development-окружение

Из каталога `backend/` (Docker Engine + Compose v2):

```sh
cp .env.example .env
# Вручную замените REPLACE_ME в .env результатом openssl rand -hex 24.
docker compose --env-file .env -f compose.dev.yaml build
docker compose --env-file .env -f compose.dev.yaml up -d db
docker compose --env-file .env -f compose.dev.yaml run --rm migrate
docker compose --env-file .env -f compose.dev.yaml up -d api
curl --fail http://127.0.0.1:18081/live
curl --fail http://127.0.0.1:18081/ready
```

Project `medexa-foundation-dev`; API доступен только на loopback, PostgreSQL не
публикует host port. Network и volume имеют project prefix, нет container_name,
external volumes/networks, bind mount Frontend или старой БД. Для второй копии
задайте `-p medexa-foundation-dev-yourname` **во всех** командах и другой API port.
Приложение работает non-root, один Uvicorn worker, без reload/proxy trust.
Dev DB использует отдельного bootstrap-owner для миграций: это не production RBAC.

Миграции запускаются явно, не при startup API. До upgrade `/live` работает, `/ready`
возвращает 503. Alembic сериализует миграторы транзакционным advisory lock.
Не запускайте эти команды на VPS или с реквизитами существующих БД.

Остановка сохраняет **новый** dev volume:

```sh
docker compose --env-file .env -f compose.dev.yaml down
```

## Локальная Python-среда

Нужны Python 3.12 и uv 0.13.6. Lock-файл фиксирует зависимости:

```sh
uv sync --locked
uv run --no-sync ruff check app migrations tests
uv run --no-sync ruff format --check app migrations tests
uv run --no-sync mypy app
uv run --no-sync pytest
```

Без `MEDEXA_RUN_DB_TESTS=1` интеграционные тесты явно skipped; unit-тестам БД не
нужна. Для native uvicorn/Alembic укажите новую локальную PostgreSQL 16 в .env:

```sh
uv run --env-file .env --no-sync alembic upgrade head
uv run --env-file .env --no-sync uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18081 --no-access-log --no-proxy-headers
```

Никогда не меняйте db_name/host на старую БД ради проверки readiness. Имена с
префиксом — дополнительный guard, не доказательство безопасности адреса.

## Полные проверки с PostgreSQL 16

```sh
export MEDEXA_TEST_DB_PASSWORD="$(openssl rand -hex 24)"
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from check
docker compose -f compose.test.yaml down
unset MEDEXA_TEST_DB_PASSWORD
```

Отдельный project `medexa-foundation-test`, сеть internal, без host ports и
постоянного volume; PostgreSQL data в tmpfs. Для параллельных запусков задавайте
уникальный `-p`. Выполните down и при ошибке. Тесты проверяют upgrade, downgrade
до base, повторный upgrade, один Alembic head, отсутствие schema drift и PG major.
Destructive migration tests отказываются запускаться без environment=test и
точного имени `medexa_foundation_test`. Не используйте pytest-xdist на одной БД.

GitHub Actions использует отдельный PostgreSQL 16 service на одноразовом runner,
Python 3.12, uv lock, Ruff, mypy, Pytest и миграционные проверки. Доступа к серверам,
GitHub write-token, production secrets, deploy или автоматическому merge нет.

## Правила идемпотентности

Будущий application service открывает `async with session.begin()` и вызывает
`run_idempotent()` с проверенным сервером actor UUID, стабильным operation,
Idempotency-Key UUID и валидированным JSON payload. Callback использует **эту же**
session, не делает commit/rollback и внешние HTTP-вызовы. Все domain writes и
response projection фиксируются одной транзакцией. Исключение должно выйти из
begin-context, чтобы он сделал rollback. Не перехватывайте его с последующим commit.
Payload включает method, resource IDs, значимые query-параметры и validated body;
одного body недостаточно для различения одинаковых операций над разными ресурсами.

Идентичный JSON независимо от порядка ключей даёт replay; иной body с тем же scope
до TTL даёт 409 IDEMPOTENCY_KEY_REUSED. Конкурирующий INSERT ждёт commit владельца;
lock timeout требует безопасного retry тем же ключом. Сохраняются только успешные
санитизированные domain projections, без Cookie/CSRF/initData/Authorization и без
request-specific meta. Последующие этапы добавят транзакционный outbox для внешних
эффектов. TTL не заменяет постоянные UNIQUE для XP/charge/entitlement.

## Ограничения безопасности и следующая работа

- Это dev/test Backend, не production-ready сервис: HMAC/CSRF/RBAC и аудит есть,
  но нет Nginx/TLS конфигурации, admin MFA, offsite backups или мониторинга.
  Rate limit login ограничен одним процессом; внешний gateway ещё не настроен.
- Не публиковать API/Swagger в интернет. Никаких реальных Telegram tokens или
  медицинских/платёжных данных для проверки этого этапа не требуется.
- JSON formatter намеренно отбрасывает произвольные сообщения библиотек и
  tracebacks. Для расследования используйте request_id/error_type, не включайте
  SQL echo или debug responses с секретами. Подробная защищённая диагностика —
  отдельная эксплуатационная задача.
- Обработчик ошибок до начала ответа даёт JSON. При сбое уже начатого streaming
  response заменить тело невозможно; streaming endpoints пока отсутствуют.
- Начальная миграция обратима **только для этого пустого foundation**; destructive
  downgrade нельзя переносить на production как стратегию восстановления.
- Контейнерные лимиты не означают измеренную вместимость VPS; текущие image tags
  следует закрепить digest после выбора production image и security review.
- Следующий этап: read-only каталог/контент. Admin HTTP-мутации закрыты до MFA.
- Runtime-образ не содержит tests/ и синтетических signing fixtures; они копируются
  только в test target.

## Проверки, RAM и откат

Результаты этапа 2: [IDENTITY_REPORT.md](IDENTITY_REPORT.md). Исторические результаты
этапа 1 и его замеры: [FOUNDATION_REPORT.md](FOUNDATION_REPORT.md).
До появления отчёта RAM на целевом VPS не считается измеренной.

Откат этой ветки — остановить **только её** Compose project и вернуться к исходному
release commit. Никаких изменений Frontend, production/preview Compose, Nginx или
существующей БД этот этап не требует. Не удаляйте чужие volumes/images через
`docker system prune`. Удаление нового dev volume допустимо только отдельно после
проверки его project label и при отсутствии нужных данных.
