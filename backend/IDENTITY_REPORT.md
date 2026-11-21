# MEDEXA Backend 2.0 — Identity/Auth/RBAC

Дата: 21 ноября 2026. Ветка `feature/medexa-backend-identity`.
База: ровно `1e6e1a83fea9abac8246666593dbed5c28844dca`, PR #22,
`feature/medexa-backend-foundation`. Target нового Draft PR — foundation, не main.

## Проверка фундамента

Проверены результаты GitHub Checks PR #22: оба check-run завершены SUCCESS.
Просмотрены settings, app factory/lifecycle, ошибки/JSON middleware, SQLAlchemy
pool/readiness/schema gate, идемпотентность, Alembic, Compose, тесты и workflow.
Фундамент соответствует этапу 1: миграции явные, PG16 и точная schema revision
проверяются readiness, DTO/ошибки не раскрывают DSN, повтор операции связывается
с domain writes одной транзакцией. Auth/roles в foundation отсутствовали намеренно.

Небольшие уточнения контракта:

- `/live` и `/ready` сохранены по реализации этапа 1, без переименования.
- Архитектурный `/api/v1/me` сохранён; запрошенный `/api/v1/users/me` — alias того
  же обработчика, с тем же DTO и проверками.
- Ранее отложенный FK idempotency actor → users добавлен новой миграцией.
- Тестовые signer/фикстуры из runtime image вынесены в отдельный test target.
- Архитектурный документ и опубликованный `0001_foundation` не изменены.

## Реализация

`app/identity/models.py`: users (включая Telegram identity и настройки), roles,
user_roles, user_sessions, auth_replays, append-only audit_events. Нет второй
дублирующей таблицы профиля или фиктивной модели администратора.

`telegram.py`: строгий однократный URL decode, HMAC SHA-256, constant-time,
auth_date≤300 секунд / future skew≤30 секунд, duplicate query/JSON rejection,
строгий bigint user ID, ограничения размера, защита canonical replay fingerprint
от перестановки полей/URL encoding. Проверенная подпись включает signature-поле.

`service.py`, `api.py`: атомарный login/upsert/replay/session/audit, непрозрачные
cookie, восстановление после restart, absolute/idle expiry, ротация при свежем
повторном login, отзыв/выход, не более 10 active sessions. Пароли/токены/raw
initData в БД и логах не сохраняются: для credentials только криптографические
хэши. CSRF воспроизводится отдельным signing key и привязан к конкретной сессии.

`security.py`, `dependencies.py`, `policy.py`: HTTPS, exact Origin/Fetch Metadata,
CSRF, body cap включая chunked, bounded per-process login limiter, глобальный
default-deny handler policy, permissions с неизвестной ролью → deny, ownership.
User → session locks в одном порядке, commit до отправки ответа. Без настроенных
секретов — 503 AUTH_NOT_CONFIGURED, никакого fallback пользователя.

`bootstrap.py`: явный операторский first-admin bootstrap, существующий active
verified User, numeric ID, обязательный --confirm, advisory lock, аудит и отзыв
старых сессий. Повтор своему admin — no-op; назначение другого через bootstrap
закрыто. Нет публичного grant/admin-bootstrap endpoint.

`maintenance.py`: явная bounded очистка истёкших replay и старых inactive sessions
по 500 записей; сохраняет users/roles/audit. Не добавляет scheduler в API.

`0002_identity`: уникальность Telegram ID/token hash, CHECK expiry/hash/status,
индексы поиска, составной FK replay→session owner, FK idempotency→user, role seed,
triggers против UPDATE/DELETE/TRUNCATE audit. Осиротевшие старые foundation cache
rows не удаляются и не превращаются в фиктивных пользователей: FK остановит upgrade.

Документация/config: `IDENTITY.md`, README, `.env.example`, dev Compose. Workflow
расширен на identity-ветку; runtime image проверяется на отсутствие tests/scripts.

## Результаты локальных проверок

| Проверка | Результат |
|---|---|
| Ruff lint / format | PASS, 39 Python-файлов |
| mypy strict | PASS, 26 app source files |
| Pytest + настоящая PostgreSQL 16.16 | **96 passed**, без skipped; Python 3.12.16 |
| Миграции | PASS: clean upgrade, downgrade base, повторный upgrade/head, один head, `alembic check` без drift |
| Docker test target | PASS: полный набор из fresh test Compose, exit code 0 |
| Docker runtime target | PASS: UID 10001, app import, отсутствуют tests/scripts/signing fixtures и pytest; network=none |
| Фиксированный crypto vector | PASS: независимо вычисленный OpenSSL HMAC; Unicode/plus/signature, без runtime signer |
| Replay/concurrency | PASS: один credential при двух конкурентных обменах; encoded/reordered proof не создаёт новую сессию |
| Сессии/CSRF | PASS: Secure/HttpOnly/SameSite=Lax/Path=/; no Domain; restore в новом app instance; expiry/idle/отзыв; key rotation; heartbeat без продления absolute |
| Негативные auth | PASS: неверный token/HMAC, подмена ID, malformed/duplicate/old/future initData, unsafe Origin/HTTP, CSRF, chunked oversize, неизвестные настройки/роли |
| IDOR/RBAC | PASS: чужая сессия и отсутствующая одинаково 404; попытка client-admin не выдаёт роль; неизвестная handler policy запрещена |
| Bootstrap/audit | PASS: несуществующий User отвергается; повтор no-op; другой User не получает admin; старые сессии отозваны; admin HTTP закрыт MFA_REQUIRED; audit immutable |
| Cleanup | PASS: expired records удаляются, active session/users/audit остаются; повтор безопасен |
| Логи | PASS: raw initData/session/CSRF не появляются в capture; validator не печатает secret input |

Тесты выполнялись в отдельном Compose project `medexa-identity-tests` без host DB
ports, с tmpfs PostgreSQL. Стенд не использует реальные аккаунты Telegram,
токены бота, пользователей или инфраструктуру. BuildKit CA передавался как
необязательный временный secret; TLS verification не отключалась. Итерационные
проверки дополнены полным fresh build/test, без изменений установленных пакетов.

GitHub Actions повторяет lint/types/PG16 tests/migrations и runtime build на
одноразовом Ubuntu 24.04 runner. Конкретный удалённый статус смотреть в Checks PR;
данный отчёт фиксирует локально выполненные проверки.

## Ограничения и следующая приёмка

1. Нет real-device Telegram iOS проверки, реального @medexapp или подключённого
   HTTPS Mini App стенда. ASGI https base_url не является браузером или реальным TLS.
   SameSite=Lax для top-level iOS требует проверки reopen/cookie persistence.
2. Strict replay при потере Set-Cookie может требовать нового запуска Mini App.
   Telegram Web iframe/third-party cookies не обещаны работающими.
3. Административный MFA, enrollment/recovery и role-management HTTP ещё отсутствуют:
   privileged permissions закрыты, а не симулируют подтверждение.
4. Runtime оставлен dev/test. Для эксплуатации нужны TLS/trusted-proxy allowlist,
   least-privilege DB roles, Nginx/gateway rate limiting, backup и security review.
   In-memory limiter поддерживает один worker, не распределённые инстансы.
5. Перед ротацией секретов оператору нужно планировать отзыв старых сессий и
   повторный вход; смена CSRF key делает старые credentials недействительными,
   но сама по себе не является массовым физическим обновлением session rows.
6. Нет изменения Frontend, content, экзаменов, XP, Premium или платежей. На целевом
   VPS 1 CPU/2 GB нагрузочные и RAM-измерения этапа 2 не проводились.

## Изоляция и откат

Все изменения ограничены новым `backend/` и его `.github` workflow. Frontend,
архитектурный документ, старый Backend, Preview/Production/VPS и действующие БД
не менялись. Merge/deploy не выполняются. Откат приложения — foundation image;
удалять таблицы пользователей/аудита через destructive downgrade на среде с
данными нельзя без отдельной backup/rollback процедуры. Тестовый downgrade
применялся только к одноразовой БД с явным guard.
