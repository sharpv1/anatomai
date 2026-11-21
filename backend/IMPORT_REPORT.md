# MEDEXA Backend 2.0 — 3b.2: Import Staging

Основа: `d190b9d00d7f33ceeb16d91878685085c580a491`.
Ветка: `feature/medexa-import-staging`; база Draft PR: `refactor/medexa-publication-policy`.

## Результат

- Один MFA/RBAC/CSRF-protected raw upload ставит XLSX/DOCX в приватную очередь.
- Пустые шаблоны с шестью обязательными колонками; optional external ID/метаданные.
- Изолированный parser subprocess: SHA-256, Office type/ZIP/XML/formula safeguards,
  hard OS limits; никакого тяжёлого разбора в HTTP.
- DB worker: singleton advisory lock, leases/fencing, роли перед каждым batch,
  staging + draft revisions/options батчами до 100 с атомарным audit.
- Предпросмотр и CSV: found/valid/errors/duplicates/drafts, координаты строки/таблицы,
  русские сообщения, signed pagination, ownership, Excel formula injection escaping.
- Стабильные auto IDs; digest reuse; exact imported-content dedup; конфликты ключей;
  отмена, crash recovery и bounded retry без повторных revisions.
- Миграция 0006: jobs/rows/content_keys и nullable revision license_reference.
  0001–0005 неизменны; published history/current pointers не меняются.
- Private retention command: raw terminal files 30 дней, orphan/work 24 часа,
  без удаления draft, отчётов или audit.

Нет медицинского reviewer/лицензионного gate, автоматической публикации, платежей,
нового тестового движка либо изменений Frontend. Инструкция API/эксплуатации:
[IMPORTS.md](IMPORTS.md), [ADMIN.md](ADMIN.md), [архитектура](../docs/MEDEXA_BACKEND_ARCHITECTURE.md).

## Проверки

Локально Python 3.12.14, PostgreSQL **16.16** в новом одноразовом tmpfs Docker-контейнере
с динамическим loopback-only портом. Рабочие базы не подключались.

| Проверка | Результат |
|---|---|
| Полный `uv run --no-sync sh scripts/check.sh` | **263 passed**, Ruff check/format, mypy — успешно |
| Последующая проверка import HTTP после дополнения OpenAPI binary contract | **16 passed** |
| Alembic | fresh upgrade, повтор upgrade, roundtrip base/head, 0006/0005 и старые transitions; schema drift отсутствует |
| Защита downgrade | 0006 отказывается терять license metadata immutable history до DDL |
| Docker runtime build | Успешно, locked dependencies, Python 3.12.16, TLS verification сохранена |
| Runtime smoke | UID 10001, no network; нет tests/scripts в image; реальный parser subprocess выполняется |
| Compose dev/test | `config --quiet` успешно, изолированные names/volumes/networks |
| Git diff | whitespace check успешен, Frontend/старые миграции не изменены |
| GitHub Actions | Настроен полный PG16/Ruff/mypy/Pytest/migrations/build/runtime-smoke gate; итог см. checks Draft PR |

Новые тесты покрывают XLSX/DOCX, пустые шаблоны, optional metadata, multiple_choice draft,
явный ключ и стабильный auto ID, неверную структуру/координаты, формулы с cached values,
DTD/entities, external links, macros/embeddings/traversal, дубли ZIP entries, ZIP bomb,
лимит строк, hash tampering, deadline/cancel subprocess, реальные OS limits,
CSV injection, MFA expiry до чтения stream, CSRF/RBAC/IDOR, private raw,
chunked upload >10 MiB, обычный JSON body limit 32 KiB, partial batch rollback/retry,
lease expiry/stale token, singleton worker lock, отзыв роли, private draft conflicts,
205 строк через несколько batch, retention и отсутствие draft в public reference API.
Существующие Foundation/Identity/Content/MFA/policy regression tests сохранены.

## Замеры ресурсов

Изолированные синтетические таблицы, не медицинский банк и не нагрузочный тест VPS.
Wall time включает запуск отдельного parser child; RSS — сообщённый Linux ru_maxrss,
который также может учитывать high-water mark процесса до exec.

| Формат | Строк | Файл, bytes | Wall, s | Разбор, ms | Peak RSS, KiB |
|---|---:|---:|---:|---:|---:|
| XLSX | 1 | 1576 | 0.170 | 4 | 48384 |
| XLSX | 1000 | 25121 | 0.279 | 156 | 53120 |
| XLSX | 5000 | 120573 | 0.764 | 638 | 72160 |
| DOCX | 1 | 995 | 0.145 | 3 | 72160 |
| DOCX | 1000 | 4690 | 0.284 | 134 | 72160 |
| DOCX | 5000 | 19030 | 0.868 | 711 | 72160 |

В runtime smoke child peak RSS 85396 KiB (около 83.4 MiB); включён импорт всего
приложения в родителе. Это не сумма RAM API + worker + PostgreSQL.
Фактические `getrlimit` подтверждены: AS 268435456 bytes, CPU 60 s,
FSIZE 67108864 bytes, NOFILE 32. Worker concurrency=1, pool=2.
Docker host имеет CgroupDriver=none: container RAM/CPU enforcement здесь **не проверен**;
Compose задаёт 512 MiB/0.5 CPU для worker на совместимом host. Целевой VPS 1 CPU/2 GB,
полный 5000-row DB throughput и одновременная пользовательская нагрузка не измерялись.
Рекомендуется отдельный acceptance/load test до будущего развёртывания.

## Ограничения / следующий этап

1. Публикация/withdraw/restore и подтверждение набора — только 3b.3; URL закрыты.
2. Дисциплины/темы должны существовать; импорт не создаёт их по догадке.
3. Только строгий текстовый OOXML по шаблону, без макросов/формул/изображений,
   сканов, старых DOC/XLS или определения правильного ответа по жирности/цвету.
4. multiple_choice сохраняется в draft, но текущая публикация/движок single_choice.
5. Exact dedup охватывает импортированные content hashes в теме; похожий медицинский
   текст — предупреждение, не семантическое слияние. Для редактирования текста вести external_id.
6. Parser subprocess имеет resource limits, но не отдельный filesystem/network namespace.
   Нужны изолированный private volume, non-root worker и обычная защита host.
7. Raw TTL ограничивает файлы; normalized staging/reports хранятся для следующего этапа.
   Нужны backup/private access и согласованный архив для долгой эксплуатации.
8. Нет административного Frontend, production-конфига или интеграции с текущим React.

## Откат

Остановить только новую dev-инсталляцию/worker, сделать backup БД/volume; использовать
forward fix. При осознанном 0006→0005 staging/jobs/dedup и draft license metadata
удалятся, сами draft вопросы сохранятся. При immutable license metadata downgrade
будет запрещён. Не откатывать схему под работающим runtime. Merge/deploy не выполнялись.

## Изменённые файлы
- `.github/workflows/medexa-backend.yml`
- `backend/.env.example`
- `backend/ADMIN.md`
- `backend/Dockerfile`
- `backend/IMPORTS.md`
- `backend/IMPORT_REPORT.md`
- `backend/README.md`
- `backend/app/admin/drafts.py`
- `backend/app/admin/schemas.py`
- `backend/app/content/fingerprints.py`
- `backend/app/content/models.py`
- `backend/app/core/config.py`
- `backend/app/core/logging.py`
- `backend/app/db/schema.py`
- `backend/app/identity/dependencies.py`
- `backend/app/identity/policy.py`
- `backend/app/identity/security.py`
- `backend/app/imports/__init__.py`
- `backend/app/imports/api.py`
- `backend/app/imports/cleanup.py`
- `backend/app/imports/errors.py`
- `backend/app/imports/limits.py`
- `backend/app/imports/models.py`
- `backend/app/imports/parser.py`
- `backend/app/imports/parser_process.py`
- `backend/app/imports/runner.py`
- `backend/app/imports/store.py`
- `backend/app/imports/templates.py`
- `backend/app/imports/worker.py`
- `backend/app/main.py`
- `backend/compose.dev.yaml`
- `backend/migrations/env.py`
- `backend/migrations/versions/0006_import_staging.py`
- `backend/pyproject.toml`
- `backend/scripts/runtime_smoke.py`
- `backend/tests/conftest.py`
- `backend/tests/test_admin_drafts.py`
- `backend/tests/test_admin_migrations.py`
- `backend/tests/test_import_migrations.py`
- `backend/tests/test_import_parser.py`
- `backend/tests/test_import_worker.py`
- `backend/tests/test_policy_migrations.py`
- `backend/tests/test_publication_policy.py`
- `backend/uv.lock`
- `docs/MEDEXA_BACKEND_ARCHITECTURE.md`
