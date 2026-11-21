# MEDEXA Backend 2.0 — этап 3a: read-only medical content

Основа: `5450646f0f896bd261a4db6f71073f1e2bf66701`, Identity PR #23;
требования — [архитектура, §5.3, §9.2, §14](../docs/MEDEXA_BACKEND_ARCHITECTURE.md).
Frontend, старый Backend, действующие БД и инфраструктура не подключены.

## Совместимость и запуск

Сохраняются транзакции Identity, HMAC/CSRF, cookies, RBAC, error envelope,
request ID, журналирование без query/body и `Cache-Control: no-store`.
Новая head — `0003_content`, строго после `0002_identity`. Старые миграции не изменены.
До явного upgrade новый `/ready` вернёт 503. Автомиграций при запуске нет.

Запуск и изолированные PostgreSQL 16 проверки — по [README](README.md).
Дополнительно задайте `MEDEXA_CONTENT_CURSOR_SIGNING_KEY`: отдельный случайный
секрет не короче 32 байт, например результат `openssl rand -hex 32`.
Не используйте bot token, CSRF key или пример из тестов. Пустое значение отключает
контентный API (503); `/api/v1/meta` продолжает честно описывать capabilities.
Смена ключа инвалидирует старые курсоры: клиент начинает загрузку сначала.

`MEDEXA_CONTENT_ASSET_DELIVERY_ENABLED=false` по умолчанию. Нет новых зависимостей.
Production-режим, настройки старого Backend и deployment в этом этапе не добавлены.

## HTTP-контракт

Префикс всех путей — `/api/v1`. UUID — строки. Объект: `{data, meta}`;
список: `{data, page: {next_cursor, has_more, total}, meta, catalog_version}`.
`meta` содержит request_id/server_time/schema_version. `total` — точное число
совпадений после фильтрации, до применения курсора. Пустая выдача — 200 и `[]`.

| GET | Доступ | Фильтры / результат |
|---|---|---|
| `/meta` | Public, без БД | brand, api_version, supported_question_kinds, capabilities |
| `/disciplines`, `/disciplines/{id}` | Public metadata | query; id/slug/title/icon_key/color_token; фактические question/topic/note_count |
| `/categories`, `/categories/{id}` | Public metadata | discipline_id, query; category и topic_count |
| `/topics`, `/topics/{id}` | Public metadata | discipline_id, category_id, query; заголовок, реальные counts, test_definition_id, available_modes |
| `/test-definitions`, `/test-definitions/{id}` | Public metadata | topic_id, query; длительность, фактический count с учётом question_limit |
| `/topics/{id}/reference-questions` | Identity + content.read | query; question_id/revision_id, исходный number, text/options/correct_option_ids |
| `/test-definitions/{id}/questions` | Identity + content.read | projection=exam\|learning, query; отдельные безопасные DTO банка, без проверки ответов |
| `/notes`, `/notes/{id}` | Identity + content.read | discipline_id, topic_id, query; опубликованные материалы; список без body |
| `/assets/{id}/download` | Identity + доступ к опубликованному конспекту | Авторизованный internal X-Accel-Redirect либо 503, если доставка отключена |

Каждый list поддерживает `cursor` и `limit`: каталог/конспекты 1–100 (default 20),
вопросы 1–30 (default 30). Query ≤200 символов, cursor ≤2048. Остальные GET не
создают попытку, не начисляют XP и не фиксируют рекомендацию. Эндпоинты
`/me/quick-practice`, `/me/daily-topic`, `/me/topics/{id}/summary` относятся к
последующим персональным модулям и здесь не имитируются.

Категория — дополнительный необязательный уровень по текущему заданию; в исходном
банке категорий нет. Не выдуманы названия/группы. Topic.category_id nullable,
составной FK гарантирует принадлежность дисциплине. Основные пути архитектуры сохранены.

Public-запросы не используют cookie, не возвращают пользовательскую статистику и
используют READ ONLY REPEATABLE READ. Закрытые запросы используют проверенную
Identity-транзакцию. Все шесть известных ролей получают `content.read`; отсутствие
роли/неизвестное право запрещены. Админские права/запись API не добавлены.

### Разделение DTO и секретов

- Catalog DTO не содержит ключи, объяснения, difficulty, авторов или права источника.
- ExamQuestionDTO и LearningQuestionDTO содержат только текст и безопасные варианты.
  SQL-проекция даже не выбирает is_correct/explanation/fingerprint. Learning feedback
  после ответа появится только вместе с серверным движком попыток.
- ReferenceQuestionDTO намеренно содержит correct_option_ids; объяснения не выдаются,
  как требуется текущему UI 8.3.2. Это закрытый справочник, не экзаменационный endpoint.
- Движок попыток отсутствует: available_modes=[] и capabilities.attempts=false.
  Обе безопасные проекции — чтение банка, не возможность начать экзамен.
- **Ограничение до этапа 4:** exam lock справочника не реализован, поскольку серверных
  active attempts ещё нет. При внедрении экзамена требуется общий пользовательский
  lock/транзакционная проверка active exam и запрет справочника до финализации.
  Этот PR не обеспечивает защищённый от списывания экзамен. Статический Frontend-банк
  остаётся без изменений и должен быть удалён из production bundle на этапе API-интеграции.

Notes body — plain_text, не доверенный HTML. Клиент обязан выводить его как текст;
не использовать dangerouslySetInnerHTML. Пустые конспекты остаются пустыми.

## Версии, фильтрация и целостность PostgreSQL

15 таблиц: disciplines, categories, topics, test_definitions, access_policies,
questions, question_revisions, question_options, topic_questions, notes,
note_revisions, assets, content_sources, legacy_mappings, catalog_state.
Миграция содержит фиксированный DDL и snapshot, не импортирует изменяемые ORM-модели.

- UUID PK, scoped UNIQUE slug, положительные duration/limits/revision numbers,
  уникальные позиции вариантов/вопросов, FK и составные owner FK.
- RESTRICT сохраняет источники, пользователей, каталог и логические объекты.
  CASCADE разрешён только внутри составных черновиков; опубликованные редакции
  защищены отдельными BEFORE-триггерами от удаления, включая каскадное.
- Индексы для status/порядка каталогов, дисциплины/темы/категории, revision owner
  и обратной связи topic_questions. Для текущего небольшого банка поиск использует
  NFC + lowercase + ё→е, AND вхождений слов, буквальные `%`/`_`, bind-параметры.
  pg_trgm/FTS и изменение семантики поиска не вводятся без EXPLAIN и измерений.
- Опубликованные/отозванные question/note revisions, options, source provenance
  и asset metadata неизменяемы. Изменение текста/ключа = новая редакция и новые UUID
  вариантов. Разрешён только status-only published→withdrawn, затем объект заморожен.
  У question/note автоматически очищается current pointer при withdraw редакции.
- Deferred constraint triggers проверяют single_choice: 2–8 вариантов, один верный;
  creator и активный content_reviewer различны, review timestamp не в будущем,
  источник проверен. Source требует license_reference и активного reviewer.
  Эти проверки подтверждают наличие approval metadata, не медицинскую/юридическую экспертизу.
- Multiple choice разрешён в draft, публикация заблокирована до поддержки клиентом
  и движком. Нельзя подключить редакцию другого вопроса или неопубликованную редакцию.
- Статусы draft/published/withdrawn; публичная выдача требует опубликованных
  родителей, источника, revision и допустимой access policy. Draft, withdrawn,
  archived, неизвестные/недоступные политики дают пустой список или 404, без
  административного обхода. Активной Premium-интеграции нет.
- catalog_state — монотонная версия, statement triggers повышают её при изменении
  контента, включая draft (консервативная инвалидация). TRUNCATE заблокирован.
  Cursor подписан HMAC, привязан к версии/пути/query/фильтрам и user_id для
  закрытой выдачи; TTL 1 час. Keyset порядок position + UUID, без OFFSET.
  Подмена/чужой query/user/path — 400 INVALID_CURSOR; новый каталог — 409 CATALOG_CHANGED.
  Private reader сравнивает версию до/после всех SQL-запросов и при гонке отклоняет выдачу.

Логика защиты рассчитана на обычного application DB user. Владелец БД/superuser,
способный отключить триггеры, остаётся привилегированной эксплуатационной границей.
Будущий этап admin/import обязан применять MFA, аудит и минимальные DB-привилегии.

## Десять исходных вопросов

Snapshot: `migrations/data/0003_legacy_questions.json`, точный источник
`src/features/tests/data.ts @ 5450646f0f896bd261a4db6f71073f1e2bf66701`.
В snapshot сохранены исходный SHA-256, тексты/варианты/ключи/объяснения; миграция
проверяет SHA-256 самого snapshot. UUID5 и legacy_mappings сохраняют соответствие ID.

**Ни один вопрос не опубликован.** Лицензии, medical reviewer и подтверждения
корректности не предоставлены. 10 revisions, их source и 4 дисциплины/темы/definitions
остаются draft; current_revision_id=NULL, reviewer=NULL. Несоответствие названия
физиологической темы содержанию не исправлено автоматически. Опубликованный каталог
после чистой миграции пуст; это безопасное состояние, а не демонстрационный банк.
Нет вымышленных конспектов. Синтетические published fixtures существуют только в тестах.

## Доставка файлов — выключена по умолчанию

API проверяет, что asset published и доступен через опубликованный конспект и
его policy. До проверки не раскрывает существование asset. Только при отдельном
включении `MEDEXA_CONTENT_ASSET_DELIVERY_ENABLED=true` возвращает:

- `X-Accel-Redirect: /internal/medexa-content/{storage_key}`;
- attachment с безопасным UUID filename, application/octet-stream, nosniff, no-store.

Контракт storage_key: две lowercase hex цифры, `/`, 64 lowercase hex цифры,
необязательное расширение `[a-z0-9]{1,10}`. Никаких URL, traversal, percent encoding,
переводов строк или произвольных filesystem paths. Некорректный key даёт 503.
storage_key отсутствует в JSON DTO. Владельцу deployment нужно отдельно настроить
Nginx `internal` location и приватный read-only asset volume, обеспечить совпадение
hash/byte_size и запрет прямой публичной раздачи. **В этом PR Nginx/volume/файлы не
настроены и реальная передача через Nginx не проверялась.** Флаг нельзя включать
при прямой публичной публикации Uvicorn: браузер не должен получать internal header.
Тесты проверяют авторизацию/заголовок/защиту пути, не подменяют такую проверку.

## Проверки и откат

Полный набор: `uv run --no-sync sh scripts/check.sh` на изолированной PostgreSQL 16;
или test Compose из README. Проверяется версия PostgreSQL, single head, upgrade,
downgrade, repeat upgrade, Alembic check без schema drift и сохранность таблиц
Identity при 0003→0002→0003. Есть негативные проверки публикации, мутаций,
чужих owner FK, статусов/политик, DTO SQL secrecy, поиска, лимитов/курсоров и файлов.

До применения к данным: backup и проверка восстановления по архитектуре. Для
локального отката остановить **новый** API, выполнить `alembic downgrade 0002_identity`
только с реквизитами новой изолированной БД. Это удаляет весь content, включая
созданные впоследствии редакции/материалы, но сохраняет Identity/Foundation.
Предпочтительный эксплуатационный откат после появления реальных данных — backup
или исправляющая forward migration, не destructive downgrade. Никаких команд на
VPS, Preview, Production или старую БД этим PR не выполняется.
