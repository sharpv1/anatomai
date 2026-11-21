# Пересмотр правил публикации вопросов

Основа: этап 3b.1, `c1dbe0b438432b1666098e08ce7beae2a12efbf8`.
Ветка: `refactor/medexa-publication-policy`; base Draft PR — `feature/medexa-backend-import`.

## Что изменилось

1. QuestionBody допускает отсутствующие/null source_id, source_reference, source_page.
   Пустые/пробельные citation/license поля нормализуются в null; фиктивных источников нет.
   LicenseReference в схеме Source и раньше nullable, теперь не блокирует публикацию.
2. Новая **0005_publication_policy** после неизменённых 0001–0004:
   - source_reference вопросов становится nullable (старый server default '' сохранён
     для совместимости старых insert; явный API null сохраняется как SQL NULL);
   - удалены обязательный source approval/licensing trigger и source independent-review CHECK;
   - question publication trigger требует структуру, а не source/medical reviewer:
     single_choice, 2–8 непустых вариантов, ровно один правильный, допустимые размеры;
   - immutable revisions/options, owner FK, draft/published/withdrawn и pointer guards сохранены;
   - legacy review metadata и существующие записи не переписываются.
3. Read models/counts вопросов больше не зависят от наличия/статуса Source.
   Статус редакции, current pointer, родители и access policy продолжают определять доступ.
   Источники-метаданные не снимают вопросы с публикации. Уже published вопросы с
   отсутствующим/draft/withdrawn Source могут стать видимыми после перехода на эту
   модель; статусы draft при этом не меняются. 10 legacy вопросов остаются draft.
4. Catalog version повышается при upgrade/downgrade политики, чтобы старый cursor
   не пропустил вопросы после изменения eligibility. Клиент перезагружает выдачу.
5. В матрице будущих permissions content_editor уполномочен публиковать свои вопросы,
   admin — свои/доступные drafts. Для импорта выделен admin-only content.import.publish.
   Обязательный второй reviewer исключён; legacy role/review fields сохранены.
6. Архитектура и ADMIN.md согласованы: upload → structural dry-run → явное admin
   confirmation → батчи ≤100. Нет отдельного approve/review шага для вопросов.
   Source/license столбцы шаблонов необязательны и могут отсутствовать. Отсутствие
   этих значений не создаёт ошибок/блокирующих предупреждений. Строки с ошибкой
   структуры не публикуются: набор нужно исправить и повторно проверить.

## Что работает сейчас и что относится к 3b.2–3b.3

Сейчас можно создавать/редактировать собственные drafts без Source через существующий
MFA-gated API. DB/read-model часть подготовлена к новым правилам, и протестирована
публикация структурно корректных вопросов без source/reviewer через PostgreSQL.

**HTTP upload/import/publish по-прежнему не зарегистрированы.** Этот PR меняет требования,
действующие DTO/валидацию/схему и дальнейший контракт, а не объявляет весь pipeline готовым.
Publishing permissions остаются fail-closed до реализации 3b.3. MFA/CSRF, ownership,
If-Match и audit существующих административных действий не ослаблены.

План 3b.2 сохраняет quarantine, SHA/type/ZIP/macro/formula guards, DB worker,
row-level report, cancel/retry/reclaim и безопасный export. Лимиты 10 MB/50 MB/
5000 строк/60 секунд не повышены. 3b.3 реализует explicit confirmation с binding к
актуальному dry-run/file/template hash, Idempotency-Key, audit, partial failures,
withdraw/restore без переписывания истории. Медицинские ответы не генерируются.
Правила review самих конспектов в этом пакете не пересматриваются.

## Проверки

- **211 passed**, Python 3.12.14, PostgreSQL **16.16**: MFA/RBAC/CSRF/IDOR, структура,
  история, optional metadata, own publication без reviewer/source, exam-safe SQL/DTO.
- Ruff check/format: PASS, 69 Python files. mypy: PASS, 41 source files.
- Миграции: single head, чистый upgrade 0001→0005, repeat upgrade, полный roundtrip,
  отсутствие Alembic drift; 0005↔0004 сохраняет строки и повышает catalog_version.
- При чистом upgrade явно выполнены deferred checks от seed 0003 до ALTER TABLE;
  это устраняет PostgreSQL pending-trigger-events error без отключения защиты данных.
- Новые HTTP/DB policy cases используют outer rollback + SAVEPOINTs. Published
  тестовая история не удаляется в обход triggers и не мешает проверкам старых версий.
- Отдельный отрицательный тест: downgrade на несовместимых данных блокируется до DDL,
  оставляя опубликованный вопрос/NULL provenance/историю неизменными.
- Runtime Docker build/smoke, Compose validation, uv lock --check, git diff --check.
  CI выполняет полный набор на PostgreSQL 16.

Тесты старой обязательной reviewer/license policy изменены по новым требованиям;
вместо запрета отсутствующих метаданных проверяется их допустимость. Отрицательные
проверки неверных/пустых вариантов, ключей, неподдерживаемых kind и нарушений доступа
сохранены/расширены. Наличие валидной структуры не публикует draft автоматически.

Локальный полный прогон выполнен из venv против отдельной tmpfs PostgreSQL в Docker
с динамическим loopback-only port. Это позволило избежать чрезмерных VFS-копий образа
тестов. Рабочие БД/сети/сервисы не использовались. Новых зависимостей нет.

## Файлы

- `docs/MEDEXA_BACKEND_ARCHITECTURE.md`: схема, роли, publish/import контракты,
  шаблоны, pipeline, критерии 3b.2–3b.3, устранение прежнего P0 reviewer/license blocker.
- `backend/ADMIN.md`, `README.md`, `CONTENT.md`: текущие правила и обозначение
  исторического документа 3a; прежние отчёты остаются снимками своих этапов.
- `backend/app/admin/schemas.py`, `drafts.py`: optional DTO, normalization и source lookup.
- `backend/app/content/models.py`, `queries.py`: nullable reference, удалённый source
  self-review CHECK и source-independent question reads/counts.
- `backend/app/identity/policy.py`, `db/schema.py`: будущие publishing permissions и head.
- `backend/migrations/versions/0005_publication_policy.py`: forward/guarded reverse DDL.
- `backend/tests/test_content_db.py`, `test_content_api.py`, `test_admin_drafts.py`,
  `test_admin_migrations.py`: обновлённые ожидания политики и совместимость миграций.
- `backend/tests/test_policy_dto.py`, `test_policy_migrations.py`, `test_publication_policy.py`:
  новые положительные/отрицательные policy/DTO/read-model/rollback cases.
- `.github/workflows/medexa-backend.yml`: проверки новой ветки.

## Откат / ограничения

После записи данных новой политики downgrade может быть невозможен без потери
смысла: прежние NOT NULL/approval/source guards им противоречат. 0005 проверяет это
**до DDL** и отказывается от отката вместо подстановки источников/медицинских approvals
или правки immutable published records. Предпочтителен forward fix/совместимый backup;
runtime/schema должны обновляться согласованно, не откатывать схему под новым API.

Исходные миграции 0001–0004 не переписаны. Frontend, main, Preview, Production,
старый Backend и действующие БД не изменены. Merge/deploy/VPS-команд нет.
