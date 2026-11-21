# Отчёт: MEDEXA Backend 2.0 — 3b.1

Ветка `feature/medexa-backend-import` от
`62eb0e4cd95106080d8fb572eed27ae923307938`.
База Draft PR — `feature/medexa-backend-content`, не main.

**Реализован только 3b.1 — MFA/admin drafts.** Разбиение 3b на три безопасных PR
предусмотрено заданием. Обработка файлов и публикация не объявлены готовыми и не
имеют публично доступных stub endpoints. Контракт и план 3b.2/3b.3: [ADMIN.md](ADMIN.md).

## Реализация и файлы

- `app/admin/models.py`, `mfa.py`: encrypted TOTP, user-bound ciphertext,
  одноразовые counters/recovery hashes, durable rate limiting, session/roles/epoch
  binding, server TTL ≤15 минут.
- `app/admin/provision.py`: приватная операторская TTY-процедура подключения и
  восстановления; без secret в argv/HTTP, с отзывом сессий и audit.
- `app/admin/auth_api.py`: CSRF-protected step-up/revoke; нет credential retrieval.
- `app/admin/schemas.py`, `drafts.py`, `api.py`, `__init__.py`: MFA-gated catalogue,
  sources и question drafts/revisions; ACL, validation, If-Match и atomic audit.
  Административные чтения также требуют MFA.
- `app/identity/policy.py`, `dependencies.py`: ограниченный список реализованных
  permissions; точное bootstrap исключение только POST/DELETE step-up. Остальные
  privileged permissions закрыты даже при grant.
- `app/content/models.py`: source creator FK/index и independent reviewer CHECK.
- `migrations/versions/0004_admin.py`: три MFA-таблицы, source ownership; frozen DDL.
- `app/core/config.py`, `app/db/schema.py`, `app/main.py`, `migrations/env.py`:
  конфигурация отдельного encryption key, новая head и router registration.
- `.env.example`, `compose.dev.yaml`: необязательный MFA key, без секретов/новых портов.
- `pyproject.toml`, `uv.lock`: cryptography 48.0.1 и зафиксированные зависимости.
- `tests/admin_helpers.py`, `test_admin_crypto.py`, `test_admin_drafts.py`,
  `test_admin_mfa.py`, `test_admin_migrations.py`, `conftest.py`: синтетические
  credentials и 52 новые проверки. Fixtures очищают только собственные test роли,
  чтобы не влиять на существующий singleton bootstrap test.
- `tests/test_content_migrations.py`: прежний явный roundtrip 0003 сохранён;
  после проверки восстановление новой head перед metadata check.
- `.github/workflows/medexa-backend.yml`: CI новой ветки.
- `README.md`, `ADMIN.md`, `ADMIN_REPORT.md`, `measurements/admin-baseline.json`:
  эксплуатация, границы этапа, проверки, измерения и откат.

Исходный архитектурный документ и миграции 0001–0003 не изменены. В существующей
модели роли называются content_editor/content_reviewer/admin; medical_reviewer
в формулировке задания соответствует content_reviewer, новой конфликтующей роли нет.

## Проверки

| Проверка | Результат |
|---|---|
| Pytest на чистой PostgreSQL 16.16, Python 3.12.16 | **199 passed**: все 147 прежних + 52 новые проверки |
| Ruff check/format | PASS, 65 Python files |
| mypy | PASS, 41 source files |
| Миграции | single head 0004_admin, upgrade, repeat upgrade, full roundtrip, 0004→0003→0004 с сохранением Content/Identity, 0003→0002→0003/head; Alembic check без drift |
| MFA | RFC vectors, ciphertext tamper/user swap/wrong key, формат, CSRF/Origin, role denial, durable lockout, concurrent replay, server freshness/future timestamp, epoch/roles/session/revocation binding, recovery single use |
| Draft admin | чужие объекты →404, reviewer read-only, published mutation →409, новые draft revisions без pointer switch, forbidden approval/owner/status fields →422, invalid options/UTF-8, source self-review CHECK |
| Atomicity/concurrency | missing/stale If-Match →412; один из двух конкурентных PATCH отклонён; duplicate external key →409 без частичной revision/audit |
| Закрытые возможности | imports/assets/review/publish/withdraw/roles HTTP не зарегистрированы; даже свежая MFA не даёт будущие publish permissions |
| Docker | runtime target собран, UID10001/read-only filesystem, imports/schema readiness PASS, tests/scripts/Pytest и test signers отсутствуют в runtime |
| Конфигурация | Compose dev/test и uv lock --check PASS; реальные секреты не использовались |

Отдельный регрессионный тест проверяет очистку истёкшей сессии с MFA grant:
удаляется только сессионный grant, credentials/recovery/audit сохраняются.
Существующий Identity maintenance не изменялся.

Миграции проверены также с нуля после окончательного добавления reviewer CHECK,
а не только на ранее созданной схеме. Реальные медицинские данные не публиковались.
TOTP/recovery используются только как синтетические fixtures. Настоящее приложение
аутентификатора/ручной TTY enrollment и Telegram iOS здесь не тестировались.

## Измерения ресурсов

Артефакт: [measurements/admin-baseline.json](measurements/admin-baseline.json).
Новый runtime image, один Uvicorn worker, приватная Docker network, без host ports.
После прогрева и 100 последовательных `/ready`:

- API process RSS/VmHWM: **94 412 KiB ≈92.2 MiB**.
- PostgreSQL: сумма PSS **35 396 KiB ≈34.6 MiB**, 7 процессов в отдельном sample.
- `/ready`: mean **2.02 ms**, p95 **2.28 ms**; это локальные health-запросы,
  не пользовательская нагрузка, не latency admin/import и не обещание throughput.

**Ограничение среды:** запрошены Docker CPU=1/RAM=384 MiB, но Docker сообщает
`CgroupDriver=none`, `MemoryLimit=false`; фактический общий cgroup — 8 GiB и CPU quota
200000/100000. Docker stats показывает общий cgroup для обоих контейнеров, поэтому
его значения не трактуются как память отдельных сервисов. Hard limits здесь не
подтверждены. RSS/PSS — наблюдения по `/proc`, не тест устойчивости на VPS 1 CPU/2 GB.
Парсер, worker peak RAM, 5000 строк/10 MB, ZIP bomb и timeout/OOM **не измерялись**,
так как эти компоненты относятся к 3b.2. Исходные лимиты задания не увеличивались.

## Оставшиеся ограничения / следующие этапы

1. **3b.2:** XLSX/DOCX templates, streaming quarantine/upload, SHA/type/ZIP validation,
   macros/externals/formulas rejection, bounded DB-backed worker, staging dry-run,
   отчёты и formula-safe export. Нужны отрицательные tests на spoofing/ZIP bombs/
   формулы/лимиты/cancel/restart; в текущем PR они не выдаются за выполненные.
2. **3b.3:** независимый reviewer approval, источник/лицензия, batches ≤100,
   permanent dedupe/idempotency, partial failure/retry, withdraw/pointer restore.
   Эти HTTP действия сейчас отсутствуют. Creator≠reviewer уже защищается для
   новых source metadata и опубликованных question revisions в БД; полного
   workflow утверждения fingerprint пока нет.
3. HTTP role management, admin notes/assets editing, WebAuthn, автоматическая
   ротация master key и recovery без одноразового кода не реализованы.
   Первый admin назначается прежней операторской bootstrap процедурой; дополнительные
   staff назначения требуют отдельной контролируемой операторской процедуры.
4. Нет production admin UI, Frontend integration, изменения auth cookies или backend
   deployment. Перед рабочим использованием нужны реальный authenticator/HTTPS smoke,
   сохранённый encryption key и проверенное восстановление backup.
5. Унаследованные gates Content API сохраняются: 10 исходных вопросов draft до
   подтверждения прав/медицинской корректности, нет attempt engine/exam lock.

Откат описан в ADMIN.md: downgrade 0004 удаляет MFA и source ownership, поэтому
после появления реальных данных предпочтителен forward fix/восстановление backup.
Нельзя откатывать схему под работающим runtime 3b.

Frontend, main, Preview, Production, старый Backend и действующие БД не изменялись.
Ничего не выполнялось на VPS. Merge и deploy не выполнялись.
