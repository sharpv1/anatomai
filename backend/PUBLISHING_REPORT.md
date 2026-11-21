# MEDEXA Backend 2.0 — 3b.3: Publication

Ветка: `feature/medexa-content-publishing`.
Основа: `d5a22d1c092947966485fe04e5a4a71e2ed2f9ca`.
База Draft PR: `feature/medexa-import-staging`.

## Реализация

- Предпросмотр import job: valid/errors/duplicates/conflicts, eligible positions,
  blocked reasons, исходный SHA/template/result version, preview hash, ETag.
- Явный admin confirmation выбранных строк; single_choice с 2–8 вариантами и
  ровно одним правильным. Ошибочные выбранные строки не пропускаются молча.
  Корректный поднабор можно подтвердить явно; excluded count остаётся в audit/report.
- Реальные файл/staging/revisions/options/parents проверяются повторно. Подтверждённый
  staging и metadata job/asset заморожены DB triggers. Редактирование draft после
  подтверждения останавливает публикацию, не изменяет согласие автоматически.
- Постоянные immutable publication_commands + существующий Idempotency-Key primitive:
  защита после истечения общего TTL и при конкурентных запросах. UNIQUE active run/job,
  immutable selection hash/count, terminal item outcomes и lease token fencing.
- Публикация пакетами ≤100, транзакционно с pointers, audit и item outcomes;
  частичный успех, cancel/retry, crash reclaim, новый явный run после max attempts.
- Editor публикует свои корректные drafts, admin — доступные; Reviewer не заменяет
  публикационное право. MFA/CSRF/Origin/ownership остаются обязательными.
- Withdraw не меняет медицинский контент. Restore published возвращает pointer;
  restore withdrawn создаёт новую опубликованную копию с новыми option IDs.
  Прежняя запись остаётся withdrawn; audit сохраняет source revision и причину.
  Повтор восстановления уже активной эквивалентной копии — unchanged.
- Existing content triggers повышают catalog_version; stale signed cursors инвалидируются,
  exam-safe DTO сохраняет отсутствие ключей ответа/объяснений.
- Один dev worker-процесс/pool=2 обслуживает импорт и публикацию через --with-imports;
  общий advisory lock ограничивает тяжёлые задания даже при двух запущенных процессах.
- Новая additive миграция 0007; **0001–0006 неизменны**, прежний immutable guard не ослаблен.
  Нет источников/лицензий/второго reviewer как обязательного gate.

Полный API-контракт и инструкции: [PUBLISHING.md](PUBLISHING.md).

## Проверки

| Проверка | Результат |
|---|---|
| Полный Pytest, PostgreSQL 16.16, Python 3.12.14 | **285 passed**, 66.96 s |
| Ruff check/format; mypy | Успешно, 60 app modules |
| Fresh / repeat upgrade, downgrade/upgrade roundtrips | Успешно; старые миграции/данные совместимы |
| Alembic schema drift | No new upgrade operations detected |
| Конкуренция | Реальные независимые HTTP transactions: same key replay; distinct keys; два admin одного import; два worker |
| Ошибки и partial outcome | Отмена между batch, сбой после flush, retry без повторных публикаций, stale lease, отозванная роль |
| Content/history | Source/license/reviewer не нужны, multiple_choice/пустой key заблокированы; withdraw/copy/pointer restore; immutable receipts/snapshots/TRUNCATE guards; downgrade refuse |
| Дополнительные focused проверки после уточнения тестов | **2 passed**: same-size file tampering и replay restore после expiry |
| Docker runtime build | Успешно, frozen dependencies, non-root; TLS verification сохранена |
| Isolated Docker runtime/parser smoke | Успешно, --network none, UID 10001, schema 0007; tests/scripts не входят в image |
| Dev/test Compose | config --quiet успешно |
| GitHub Actions | Полный gate настроен: PG16/Pytest/Ruff/mypy/migrations/build/parser smoke и read-only combined-worker readiness smoke; итог в checks PR |

Новые сценарии используют только синтетические вопросы. Большинство тестов публикации
откатывает внешнюю транзакцию, не удаляя immutable историю. Для реальной конкуренции
создаются/удаляются отдельные одноразовые БД на изолированном PostgreSQL 16; тестовой
роли нужен CREATEDB. Production credentials для этих тестов использовать нельзя.

Проверены 205 вопросов через настоящие batch по 100, защита полного batch от stale item,
реальные структурные guards, старые курсоры, неподдерживаемые вопросы, доступ к чужим
черновикам, MFA expiry/CSRF, сохранение принятой команды после удаления auth session,
замороженный staging и подмена файла той же длины (проверка фактического SHA-256).

## Ограничения среды и замеров

Runtime/parser smoke сообщил peak ru_maxrss 85744 KiB (около 83.7 MiB), OS limits
AS=256 MiB, CPU=60 s, FSIZE=64 MiB, NOFILE=32. Это не замер всего backend/VPS.

Локальный Docker использует VFS. Попытка одновременно запустить runtime-контейнер и
PostgreSQL-контейнер упёрлась в диск execution workspace; это infrastructure failure,
не успешно пройденный локальный combined-worker DB smoke. Одноразовые контейнеры
остановлены, старые собственные validation images очищены, isolated runtime smoke
повторён успешно. Проверка Docker combined-worker с PostgreSQL перенесена в CI
на чистый runner; результат следует смотреть в checks PR.

Целевой VPS 1 CPU/2 GB, полный 5000-row publish throughput, общий peak RAM и cgroup
RAM/CPU enforcement здесь не измерялись. Production/VPS не подключались.

## Ограничения продукта

1. Только single_choice. Multiple-choice хранится draft, без нового движка.
2. Публикация metadata дисциплин/тем не выполняется автоматически. Нужны реальные
   связи; при draft-родителях preview предупреждает, что вопрос не виден в каталоге.
3. Raw TTL 30 дней сохраняется; активный run защищён от cleanup. После expiry raw
   доступны отдельные явные операции с draft revision, не фиктивная проверка файла.
4. Отчёт run показывает исторические outcomes, а не отменяет их после будущего withdraw.
5. Принятая команда переживает обычное expiry сессии/MFA; блокировка/отзыв admin и
   cancel останавливают pending. Для новых команд нужна свежая MFA.
6. Нет attempts, XP, Premium, платежей, административного UI и React-интеграции.

## Следующий этап

Этап 4 архитектуры: серверный движок attempts. Фиксировать revision_id и option_id
каждого item при старте попытки; не получать исторические ответы через current pointer.
Отдельно реализовать learning/exam, серверный deadline, idempotent submit/advance/finish,
атомарный finalization и resume. До UI-интеграции выполнить нагрузочный gate 1 CPU/2 GB,
restore-test backup/private volume и проверку реального Telegram iOS auth flow.

## Откат

Предпочтителен forward fix. 0007→0006 допускается только без publication receipts/runs;
при наличии истории миграция отказывается её терять. Остановить только новую dev среду,
согласовать код/схему и backup; не откатывать схему под работающим новым runtime.
Изменений на main, Preview, Production, старом Backend и Frontend нет. Merge/deploy нет.

## Изменённые файлы
- `.github/workflows/medexa-backend.yml`
- `backend/ADMIN.md`
- `backend/IMPORTS.md`
- `backend/PUBLISHING.md`
- `backend/PUBLISHING_REPORT.md`
- `backend/README.md`
- `backend/app/core/logging.py`
- `backend/app/db/schema.py`
- `backend/app/identity/policy.py`
- `backend/app/identity/service.py`
- `backend/app/imports/api.py`
- `backend/app/imports/cleanup.py`
- `backend/app/imports/worker.py`
- `backend/app/main.py`
- `backend/app/publishing/__init__.py`
- `backend/app/publishing/api.py`
- `backend/app/publishing/models.py`
- `backend/app/publishing/service.py`
- `backend/app/publishing/snapshots.py`
- `backend/app/publishing/worker.py`
- `backend/compose.dev.yaml`
- `backend/migrations/env.py`
- `backend/migrations/versions/0007_publishing.py`
- `backend/scripts/runtime_smoke.py`
- `backend/tests/conftest.py`
- `backend/tests/test_admin_drafts.py`
- `backend/tests/test_admin_mfa.py`
- `backend/tests/test_import_migrations.py`
- `backend/tests/test_policy_dto.py`
- `backend/tests/test_publication_policy.py`
- `backend/tests/test_publishing.py`
- `backend/tests/test_publishing_concurrency.py`
- `docs/MEDEXA_BACKEND_ARCHITECTURE.md`
