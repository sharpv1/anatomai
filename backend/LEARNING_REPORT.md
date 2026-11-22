# MEDEXA Backend 2.0 — Learning Attempts (4a)

Ветка: `feature/medexa-learning-attempts`.
Основа: `f001e3e3a12d18f96182c87881ad3286ac039c96`.
База Draft PR: `feature/medexa-content-publishing`.

## Что реализовано

- POST attempts по дисциплине/теме/test definition для авторизованного пользователя.
  Только доступные опубликованные current single_choice; непустой ordered_all v1,
  до 5000 уникальных вопросов, детерминированные порядок/дедупликация дисциплины.
- Серверный sealed snapshot question/revision/option IDs и порядка; исходный Content
  не копируется в параллельный банк. Scope/title/catalog_version/policy/epoch/timezone
  сохраняются; дальнейшая публикация/withdraw/restore не меняют начатую попытку.
- Learning submit → immutable ответ и feedback (правильность/ключ/существующее объяснение).
  Advance, skip, early finish с skipped хвостом, abandon без результата, resume/active.
- Раздельные safe DTO awaiting_answer/checked (extra=forbid). До submit нет ключей,
  explanation или фиктивного result. Счёт/процент/время не принимаются с клиента.
- Серверный immutable результат correct/wrong/skipped/answered/ROUND_HALF_UP percent
  и wall-clock duration. Никаких XP/statistics/profile history projections.
- Idempotency-Key + исходный If-Match, user→attempt locks, одна active/user, version,
  ownership/CSRF. Постоянные compact receipts после общего cache TTL восстанавливают
  **исходную** позицию/checked state, а не текущий вопрос после дальнейшего advance.
- Миграция 0008: attempts/items/item_options/responses/commands, composite FK,
  seal/immutable/score/version/result guards. 0001–0007 не переписаны.

[API-контракт и эксплуатация](LEARNING.md). Архитектура обновлена отдельным срезом 4a.

## Проверки

| Проверка | Результат |
|---|---|
| Полный `scripts/check.sh`, Python 3.12.14, PostgreSQL 16.16 | **307 passed**, 83.55 s |
| Ruff check/format; mypy | Успешно, 65 app modules |
| Fresh/repeat upgrade, downgrade/upgrade roundtrip | Успешно; старые этапы 1–3b.3 проходят regression tests |
| Alembic schema drift | No new upgrade operations detected |
| Docker runtime build | Успешно, frozen dependencies, non-root, TLS verification сохранена |
| Docker runtime/parser smoke | Успешно, UID 10001, --network none, schema 0008; tests/scripts отсутствуют в image |
| CI | Настроен полный PG16/Pytest/Ruff/mypy/migrations/build/runtime smoke gate новой ветки; итог — checks PR |
| Diff scope | Только backend/docs/его workflow; Frontend и 0001–0007 неизменны |

Основные новые сценарии:

- три scope, только опубликованные вопросы, safe projections и resume;
- выбор другого question option, повторный submit/skip, прежняя версия и item;
- правильный/неправильный ответ, объяснение только checked, skipped last/early finish;
- 0/13/88/100% (включая ROUND_HALF_UP 12.5→13 и 87.5→88), server duration;
- empty/unavailable банк, unsupported definition/Exam, подмена score/time;
- ownership даже для admin, CSRF, active conflict;
- исходный snapshot после withdraw и новой публикации с другими текстами/вариантами;
- immutable snapshots/responses/results/receipts, TRUNCATE guards и запрет downgrade history;
- ответ без version increment и поддельная правильность отвергаются PostgreSQL;
- same-key replay после 7-дневного expiry, включая старый start/submit/advance после
  завершения и маскировку feedback у первоначально непроверенного следующего вопроса;
- fault до commit после flush ответа: rollback и retry тем же ключом;
- **реальные независимые PostgreSQL транзакции**: параллельный start, submit, advance,
  finish; конкурирующие разные варианты/ключи → ровно один committed ответ;
- новый экземпляр API с новым DB pool и теми же cookies видит сохранённый checked state
  и результат; модель потери HTTP-ответа после commit не создаёт второй ответ;
- 500-question snapshot + early finish: весь хвост skipped, deferred guards проверены;
- дисциплина дедуплицирует question IDs из нескольких тем.

Большинство тестов откатывает внешнюю транзакцию, не удаляя immutable историю.
Конкурентные проверки используют отдельную одноразовую БД на изолированном PostgreSQL
и реальные commits. Тестовой роли нужен CREATEDB. Production credentials не использовались.
Новый экземпляр API/потеря ответа моделируются ASGI; реальный TCP disconnect/kill на VPS
в этой среде не выполнялся.

## Ресурсы и ограничения

Runtime/parser smoke: Linux ru_maxrss 86420 KiB (около 84.4 MiB) для parser child,
включая возможный inherited high-water mark; это **не** общий RAM backend/VPS.
Действующие OS limits парсера — AS=256 MiB, CPU=60 s, output=64 MiB, NOFILE=32.
Для Learning не добавлены процессы/worker/зависимости. PostgreSQL был одноразовым
контейнером с tmpfs и динамическим loopback-only портом; перед Docker build он удалён.

На целевом VPS 1 CPU/2 GB не измерялись peak RAM, p95, максимальный 5000-question
throughput и суммарный рост БД/кеша. Нужен отдельный нагрузочный и retention gate до
Production. На старте выбор ≤5000 проверяется целиком, не режется молча.

Learning без дедлайна и скрытого idle TTL: активная попытка остаётся для resume/abandon.
Result-review, история профиля, статистика, reset, повтор ошибок, Exam, XP, Premium,
Stars/платежи и React не реализованы. Общий idempotency cache содержит private ответы
до операционной очистки; compact business receipts и attempt history сохраняются.
Retention/backup/анонимизация должны быть согласованы до реальных данных.

## Следующий этап

4b: Exam draft/advance/deadline/finalizer поверх того же snapshot, без утечки ключей,
server timeout и гонки finish↔timeout. Затем отдельные статистические проекции/history
и только после этого интеграция React с сохранением дизайна. Для Production также
необходимы restore-test backup, нагрузочный gate и Telegram iOS cookies/reopen.

## Откат

Предпочтителен forward fix. 0008→0007 отказывается терять learning history при наличии
attempts/commands; не удалять ответы ради отката. Код/схему/backup согласовывать вместе.
Ничего не менялось на main, Preview, Production, старом Backend или работающих БД.
Merge/deploy/VPS-команд нет.

## Изменённые файлы
- `.github/workflows/medexa-backend.yml`
- `backend/LEARNING.md`
- `backend/LEARNING_REPORT.md`
- `backend/README.md`
- `backend/app/attempts/__init__.py`
- `backend/app/attempts/api.py`
- `backend/app/attempts/models.py`
- `backend/app/attempts/schemas.py`
- `backend/app/attempts/service.py`
- `backend/app/db/schema.py`
- `backend/app/identity/policy.py`
- `backend/app/main.py`
- `backend/migrations/env.py`
- `backend/migrations/versions/0008_learning_attempts.py`
- `backend/scripts/runtime_smoke.py`
- `backend/tests/conftest.py`
- `backend/tests/test_content_api.py`
- `backend/tests/test_import_migrations.py`
- `backend/tests/test_learning_attempts.py`
- `backend/tests/test_learning_concurrency.py`
- `backend/tests/test_publication_policy.py`
- `docs/MEDEXA_BACKEND_ARCHITECTURE.md`
