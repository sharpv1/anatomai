# MEDEXA Identity — контракт и безопасная работа

Этап 2 архитектуры, основан на проверенном foundation `1e6e1a8` / Draft PR #22.
Frontend и старый Backend не интегрированы. Production-режим не добавлен:
`MEDEXA_ENVIRONMENT` по-прежнему допускает только development/test.

## Настройки

| Переменная | Правило |
|---|---|
| `MEDEXA_TELEGRAM_BOT_TOKEN` | Токен собственного отдельного тестового бота; без Git и command-line аргументов |
| `MEDEXA_CSRF_SIGNING_KEY` | Независимый постоянный секрет ≥32 байт; генерировать криптографически, например `openssl rand -hex 32` |
| `MEDEXA_APP_ORIGIN` | Единственный точный HTTPS origin Mini App, без path/query/credentials; по умолчанию https://localhost |
| `MEDEXA_INIT_DATA_MAX_AGE_SECONDS` | 300 по умолчанию; можно уменьшить, нельзя повысить выше 300 |
| `MEDEXA_SESSION_ABSOLUTE_SECONDS` | 604800, максимум 7 суток |
| `MEDEXA_SESSION_IDLE_SECONDS` | 86400, максимум сутки, всегда ограничен абсолютным сроком |
| `MEDEXA_LOGIN_RATE_LIMIT` | 10 запросов в минуту на наблюдаемый IP, один worker |

Пустой bot token/CSRF key означает disabled, **не** тестовую авторизацию. Если
хотя бы один секрет не задан, обмен initData возвращает 503 AUTH_NOT_CONFIGURED.
Не генерировать signing key при каждом startup: сохранённые сессии должны
восстанавливаться после перезапуска. Смена ключа инвалидирует старые сессии;
восстановление требует нового свежего Telegram proof. Настройки и сообщения об
ошибке конфигурации скрывают входные значения.

Секреты хранить в защищённом environment/локальном `.env` с правами 0600, не в
`VITE_*`, URL, bash history, PR, issue, CI output или Docker build args. Dev Compose
передаёт три первые настройки, остальные можно задать локальным override.
Test Compose не передаёт bot token: тестовые ключи создаются **только фикстурами**.

## HTTPS, cookies и Telegram iOS

Все `/api/v1/*` требуют настоящего HTTPS scheme. `X-Forwarded-Proto` от клиента
не делает HTTP безопасным: runtime Uvicorn по-прежнему не доверяет proxy headers.
Dev Compose HTTP port предназначен для `/live` и `/ready`. Для ручного auth-теста
нужен отдельно настроенный локальный TLS либо проверенный reverse proxy с точным
allowlist доверенных proxy; конфигурация действующего Nginx этим PR не меняется.
Нельзя отключать Secure cookie ради curl по HTTP.

Cookie `__Host-medexa_session`: HttpOnly, Secure, SameSite=Lax, Path=/, без Domain.
Токен — 32 случайных байта, base64url; в PostgreSQL только SHA-256. Зафиксированы
absolute и idle expiry; last_seen/idle продлеваются не чаще раза в 5 минут и не
продлевают absolute. До 10 активных сессий на пользователя, старейшая отзывается
при превышении. Список не выдумывает устройство/ОС: user agent не хранится.

Для целевого top-level Telegram iOS WebView предполагается same-origin Frontend
и API. **Настоящий Telegram iOS WebView в рамках этого этапа не проверен**: нет
подключённого тестового бота и HTTPS Mini App стенда. ASGI HTTPS-клиент проверяет
заголовки и контракт, но не реальную cookie persistence/Safari ITP. Telegram Web
iframe/third-party cookies не заявлены поддержанными; SameSite=None не включается
автоматически. На реальном iPhone до включения нужны login → reopen → restore,
idle expiry, logout, потеря сети/ответа и смена пользователя.

## Доверие initData и replay

Принимается raw `initData` только JSON-body. Лимит строки 16 KiB, HTTP body 32 KiB,
включая chunked запросы. Разбор URL ровно один раз; duplicate query/JSON fields,
malformed encoding/hash, нецелый/неположительный Telegram ID отвергаются.

HMAC: secret=HMAC-SHA256(key="WebAppData", message=bot_token); затем HMAC secret
по отсортированным `key=value` через LF. Исключён только hash, signature сохранён.
User JSON не пересериализуется перед проверкой. Сравнение constant-time.
auth_date проверяется после подписи: не старше 300 секунд, не более 30 секунд
в будущем. Telegram ID берётся только из проверенного user; username, is_admin,
is_premium и прочие клиентские признаки никогда не дают роли.

Replay fingerprint основан на проверенной подписи и bot ID, а не raw query:
перестановка параметров, другой регистр hex и эквивалентное URL-кодирование не
создают новый credential. Upsert пользователя/replay/сессии/аудита — одна транзакция,
с сериализацией по проверенному Telegram ID. В сессиях и auth_replays нет raw proof.
FK привязывает replay к **тому же владельцу**, что у session.

Повтор свежего proof с действующей сессией того же пользователя возвращает её,
не создаёт новую cookie. Без подходящей сессии — 409 AUTH_RELAUNCH_REQUIRED.
Новый свежий proof с той же активной identity ротирует credential/CSRF и отзывает
старую сессию. Proof другой identity не переключает активную сессию: сначала logout.
Потеря первого Set-Cookie/ответа может потребовать повторного открытия Mini App:
это сознательный strict-replay контракт, а не повод сохранять initData в localStorage.
Украденное свежее initData до первого обмена остаётся bearer-доказательством;
TLS, отсутствие логирования и защита Frontend от XSS обязательны.

## API

Префикс `/api/v1`; ответы `data + meta`, ошибки `error.code/message/details/request_id`.
Персональные ответы no-store. Raw session token никогда не входит в JSON.

| Endpoint | Контракт |
|---|---|
| POST `/auth/telegram` | `{init_data, timezone?, language?}`, точный Origin; Set-Cookie + user/session/CSRF после commit |
| GET `/auth/session` | Восстановление из cookie, user/session/expiry и воспроизводимый csrf_token |
| GET `/me` | Собственный профиль, числовой Telegram ID десятичной строкой, roles, version; strong ETag `"1"` |
| GET `/users/me` | Запрошенный в задании alias **того же** `/me`, не параллельная модель |
| PATCH `/me/preferences` | Непустой subset `{timezone, language}`; CSRF + Origin + If-Match; IANA timezone, BCP-style language; роли/user_id запрещены |
| GET `/me/sessions` | Только собственные действующие сессии; ID/время/current, без credential/hash/fingerprint |
| DELETE `/me/sessions/{id}` | Только своя сессия; CSRF + Origin; чужая и отсутствующая одинаково 404; текущая удаляет cookie |
| POST `/auth/logout` | Origin; при распознаваемой сессии CSRF, включая повтор с уже отозванным токеном; 204 и удаление cookie; отсутствие cookie — безопасный 204 |

Мутации с существующей сессией требуют `X-CSRF-Token` из `/auth/session` и точного
Origin; cross-site Fetch Metadata запрещены. Первичный login защищён Origin,
HTTPS, свежим подписанным proof и rate limit. Logout без распознаваемого credential
может только удалить неработающую cookie и не меняет чужой аккаунт.
CORS не включён, wildcard credentials отсутствуют. Для Preferences If-Match
обязателен: отсутствующий/неправильный формат →412, устаревшая версия →409.

Основные ошибки: 401 INIT_DATA_INVALID/INIT_DATA_EXPIRED/AUTH_REQUIRED/SESSION_EXPIRED,
403 ORIGIN_DENIED/HTTPS_REQUIRED/CSRF_INVALID/USER_BLOCKED/ACCESS_DENIED/MFA_REQUIRED,
409 AUTH_RELAUNCH_REQUIRED/SESSION_IDENTITY_MISMATCH/USER_VERSION_CONFLICT,
413 REQUEST_TOO_LARGE, 422 VALIDATION_ERROR, 429 RATE_LIMITED, 503 AUTH_NOT_CONFIGURED.
Неисправная БД возвращает безопасный 503 без SQL/DSN.

## RBAC, ownership и транзакции

Глобальная FastAPI dependency требует явной policy для каждого API-handler;
новый handler без policy получает ACCESS_DENIED. Public allowlist — health,
Telegram exchange и безопасный self-logout. Все остальные permissions задаются
сервером: student, content_editor, content_reviewer, support, billing_admin, admin.
Неизвестная роль/permission по умолчанию ничего не разрешает.

Свой пользователь выбирается из проверенной session, а не query/body user_id.
Session revoke фильтрует и ID, и owner. User → session locks используются в одном
порядке при авторизации, обновлении, отзыве и bootstrap. Изменения коммитятся до
отправки ответа; ошибка откатывает всю операцию. Роли читаются из БД, не cookie.
Заблокированные/anonymized пользователи не проходят восстановление.

Административных business endpoints ещё нет. Даже роль admin не разрешает
административную HTTP-мутацию без MFA: такие permissions пока возвращают
MFA_REQUIRED. Step-up MFA, enrollment/recovery и полноценный role-management API
относятся к отдельному административному этапу, не имитируются.

## Операторский bootstrap

Только существующий active User, ранее созданный проверенным Telegram login.
Первый admin назначается локальной CLI с явным подтверждением и DB credentials:

```sh
# NUMERIC_ID заменить на проверенный Telegram ID, не username.
uv run --env-file .env --no-sync python -m app.identity.bootstrap --telegram-user-id NUMERIC_ID --confirm
```

CLI не создаёт пользователя, не принимает bot/admin secret из аргументов и не
публикуется через HTTP. Глобальный advisory lock защищает первый bootstrap;
повтор для того же единственного admin ничего не меняет, другой пользователь
получает BOOTSTRAP_CLOSED. Назначение записывается в audit, все прежние сессии
отзываются. После этого требуется новый login; административные HTTP-права всё
равно закрыты до MFA. CLI печатает только результат/безопасный error code.

## Миграции, аудит и обслуживание

Head `0002_identity`: users, roles, user_roles, user_sessions, auth_replays,
audit_events; FK idempotency actor → users; ограничения expiry/hash/status,
уникальные Telegram ID/token hashes, composite session-owner FK и индексы.
Опубликованный `0001_foundation` не переписывался. Настройки находятся в users:
отдельная дублирующая таблица с профилем не создаётся.

Если в dev-БД остались foundation cache rows с actor_id без существующего User,
upgrade **останавливается** на FK. Не создавать фиктивных пользователей и не
отключать constraint: отдельно проверить/очистить только disposable cache перед
повтором. Миграция не удаляет такие записи автоматически. На пустой новой БД
upgrade/downgrade/повторный upgrade и schema drift проверяются CI на PG16.

Audit append-only защищён triggers от UPDATE/DELETE/TRUNCATE; содержит события,
UUID и безопасные metadata, без token/initData/CSRF. Dev owner может изменить
DDL: до Production нужны отдельные least-privilege app/migrator DB roles.

Очистка выполняется явно оператором, без scheduler внутри API:

```sh
uv run --env-file .env --no-sync python -m app.identity.maintenance --confirm
```

За вызов до 500 replay records, истёкших более суток назад, и до 500 inactive
sessions старше 30 дней без replay-ссылок. Пользователи/роли/audit не удаляются;
счётчики очистки аудируются. Несколько вызовов безопасны. Clock/NTP должны быть
надёжными; календарные настройки пользователя не участвуют в сроках credential.

## Проверки и ограничения

`uv run --no-sync sh scripts/check.sh` и test Compose из README. Для PG-тестов
обязательны environment=test, отдельная БД `medexa_foundation_test` и явный
MEDEXA_RUN_DB_TESTS=1. Синтетический bot signer находится только в tests,
test image и одноразовом CI, runtime image его не содержит. Auth тестируется
на настоящей PostgreSQL 16, не SQLite, без реальных Telegram аккаунтов/токенов.

Не выполнены: реальная авторизация @medexapp, Telegram iOS WebView, поддержка
iframe, TLS/reverse-proxy эксплуатационная интеграция, админский MFA, распределённый
rate limit и нагрузочное испытание VPS. Нельзя трактовать зелёные mock/ASGI тесты
как доказательство этих сценариев. Login limiter in-memory рассчитан на один
worker; перед proxy/multi-instance релизом нужен проверенный gateway/общий limiter.

Откат к foundation возможен остановкой только dev/test проекта и возвратом
image/ветки. Destructive downgrade с пользовательскими данными не является
production-стратегией: перед изменениями схемы нужны backup и отдельное согласование.
