# Этап 3a — отчёт реализации

Ветка: `feature/medexa-backend-content` от точного Identity commit
`5450646f0f896bd261a4db6f71073f1e2bf66701`. База Draft PR:
`feature/medexa-backend-identity`. Foundation PR #22 и Identity PR #23 проверены:
их GitHub Actions прошли; унаследованные тесты включены в общий прогон.

Основной контракт и эксплуатационные ограничения: [CONTENT.md](CONTENT.md).
Архитектурный документ сохранён без изменений.

## Изменённые файлы

- `backend/app/content/__init__.py`, `models.py`: 15 таблиц контента и связи.
- `backend/app/content/schemas.py`: независимые catalog/reference/learning/exam DTO.
- `backend/app/content/queries.py`: единые фильтры публикации, источников и доступности.
- `backend/app/content/cursors.py`, `service.py`: поиск, bounded keyset pagination,
  HMAC/version/user scope, согласованность чтения.
- `backend/app/content/api.py`: GET-каталог, категории/темы/definitions, reference,
  safe question bank, notes и авторизованный file offload.
- `backend/migrations/versions/0003_content.py`: фиксированный DDL, индексы/FK,
  publication/immutability/version triggers, quarantine seed и downgrade.
- `backend/migrations/data/0003_legacy_questions.json`: неизменяемый snapshot 10 вопросов.
- `backend/app/main.py`, `core/config.py`, `db/schema.py`, `migrations/env.py`:
  подключение router/metadata, новая head и конфигурация.
- `backend/app/identity/dependencies.py`, `identity/policy.py`: отдельная публичная
  read-only транзакция и content.read без изменения auth/session/CSRF алгоритмов.
- `backend/tests/conftest.py`: metadata и синтетические fixtures, только test DB.
- `backend/tests/test_content_api.py`, `test_content_db.py`, `test_content_cursors.py`,
  `test_content_migrations.py`: 51 новая проверка API/БД/курсоров/миграций.
- `backend/.env.example`, `compose.dev.yaml`: optional key/asset flag, без секретов.
- `.github/workflows/medexa-backend.yml`: CI для новой feature-ветки.
- `backend/README.md`, `CONTENT.md`, `CONTENT_REPORT.md`: запуск, контракт,
  ограничения, проверки и безопасный локальный откат.

## Проверки

| Проверка | Результат |
|---|---|
| Pytest, Python 3.12 / PostgreSQL **16.16**, изолированный Docker network/tmpfs | **147 passed**, включая 96 унаследованных проверок |
| Ruff check + format | PASS, 51 Python files |
| mypy | PASS, 33 source files |
| Alembic | single head 0003_content; upgrade с 0002; 0003→0002→0003 сохраняет Identity; полный downgrade base→upgrade; повторный upgrade; check без drift |
| Snapshot | Все 10 questions/revisions — draft, reviewer отсутствует, current pointer отсутствует; нет опубликованного исходного банка/конспектов |
| Secrecy | Exam/learning responses и SQL-проекции не содержат ключи, explanation, fingerprint, difficulty |
| Доступ | 401 без сессии, 403 без роли; draft/withdrawn/запреты родителей и policies →404/пустая выдача; нет write API |
| Пагинация | Пределы, поиск ё/е и буквальных wildcard, стабильная нумерация, cursor tamper/query/path/user/TTL/version |
| Исторические данные | Нельзя изменить/удалить published revision/option/source/asset; foreign owner и draft pointer отклонены |
| Docker | runtime target собран; non-root UID10001, imports/snapshot OK; tests/scripts/Pytest не входят в runtime |
| Compose / lock / Git | Обе конфигурации валидны без печати env; uv lock --check и git diff --check PASS |

Никакие тесты не используют действующую БД или настоящий bot token. Материалы
с настоящими правами/медицинским approval не публиковались; published fixtures —
только синтетические служебные строки в test DB. Дополнительный trusted CA для
локального Docker build передан через необязательный BuildKit secret, TLS-проверка
сохранена. Никаких новых зависимостей.

## Ограничения и следующие этапы

1. Для 10 вопросов не получены лицензии/медицинское одобрение; опубликованный каталог
   после чистой миграции пуст. Требуется reviewer, проверка классификации физиологии
   и прав на тексты перед отдельной публикацией.
2. Admin/edit/import/attempt engine, активный exam lock, XP, персональные summaries,
   рекомендации и Premium/payment не реализованы. Экзаменационные ключи в safe API
   отсутствуют, но reference намеренно выдаёт правильные ответы авторизованному
   пользователю. Не включать серверные экзамены до exam lock и удаления статического
   Frontend-банка при последующей интеграции.
3. Файловый offload выключен. Авторизация и X-Accel заголовки проверены в ASGI;
   приватный volume, реальный Nginx internal location и передача файла здесь не
   настроены/не проверялись. Нужен отдельный инфраструктурный этап.
4. API не подключён к React; внешний вид и действующий пользовательский интерфейс
   не меняются. Реального iOS/Telegram тестирования этот backend PR не заявляет.
5. Нагрузочное тестирование большого медицинского банка и измерение целевого VPS
   не проводились. Поиск малого банка без pg_trgm; индексы расширять по измерениям.

Frontend, старый Backend, main, Preview, Production и MEDEXA-инфраструктура не
изменялись. Merge, deploy и команды на VPS не выполнялись. Инструкция локального
отката с предупреждением об удалении content находится в CONTENT.md.
