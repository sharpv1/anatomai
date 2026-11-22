# MEDEXA Backend 2.0 — Exam Engine (4b)

Ветка: `feature/medexa-exam-attempts`.
Основа: `1a598f4425ad9497f6fb60b6a999266816cc2b21`.
База Draft PR: `feature/medexa-learning-attempts`.

## Реализация

- Exam на существующем механизме snapshot по discipline/topic/test definition.
  Опциональное количество вопросов, без добавления, повторов и скрытого изменения N.
- Только опубликованные доступные single_choice. Фиксация revision/option IDs,
  порядка и исходного title/catalog_version. Изменения банка не меняют начатую попытку.
- PostgreSQL started_at/deadline_at, server remaining_seconds, immutable deadline.
  Выбор длительности: определение теста либо явно описанная серверная политика v1
  для topic/discipline (60 с/вопрос, максимум сутки); клиент время не задаёт.
- Изменяемый Exam draft, очистка, произвольный переход по позициям и возврат к ответам.
  Learning submit запрещён в Exam; Learning draft/navigate не доступны.
- Единая атомарная финализация для finish/last/timeout; immutable responses и результат.
  Пропуски учитываются отдельно, процент и длительность вычисляет сервер.
- Отдельный лёгкий DB-backed finalizer: poll 2 с, индекс deadline, SKIP LOCKED,
  одна попытка/транзакция, общий lock order user→attempt. Redis/Celery не добавлены.
- Lazy timeout при resume/active/result/команде, background completion при закрытом
  клиенте, безопасное продолжение после rollback/restart worker.
- Строгие раздельные Exam/Learning DTO. Нет correctness/ключей/объяснений/score в active
  Exam. Порционный snapshot review открывается только после фиксации результата.
  Reference API блокирует выдачу ключей во время активного Exam.
- Ownership (включая admin), CSRF, Idempotency-Key/If-Match/CAS. Компактные постоянные
  receipts сохраняют исходный выбор/позицию/версию, без копирования медицинского банка.
  Канонический hash старта Learning и старые receipts остаются совместимыми с 0008.
- Миграция 0009; 0001–0008 не изменены. Существующие Learning-история, ответы и ключи
  проходят downgrade 0009→0008 / повторный upgrade с восстановлением и replay.

[API-контракт, политика времени и эксплуатация](EXAM.md).

## Проверки

- Финальный полный локальный Pytest на Python 3.12.14 / PostgreSQL 16.16:
  **327 passed, 110.62 s**, включая сохранение Learning-истории при 0008→0009.
- Ruff check + format, strict mypy: успешно, 67 app modules.
- Fresh/repeat upgrade, downgrade/upgrade, Alembic schema drift: успешно.
- Docker runtime build: успешно, frozen dependencies, non-root UID 10001,
  TLS verification включена; тестовые credentials/scripts не помещаются в image.
- Runtime smoke внутри построенного image: реальный HTTP по loopback `/live` и
  `/ready` против одноразового PG16, импорт API, schema 0009 и finalizer poll — успешно.
- Runtime/parser smoke с `--network none`: успешно, count=1, elapsed=4 ms;
  parser max_rss=86672 KiB — **это не RAM API/finalizer/VPS**.
- Изолированные Compose dev/test config: успешно; отдельный dev profile `exams`,
  finalizer mem_limit=192m. Полная RAM/нагрузка на 1 CPU/2 GB не измерялась.
- CI выполняет полный Pytest/PG16/Ruff/mypy/migrations, build, parser smoke,
  publishing/import worker smoke и новый finalizer/HTTP runtime smoke.
  Окончательный статус — checks Draft PR на опубликованном коммите.

Новые сценарии:

1. Три scope, выбор N, неправильные count/option/deadline/score, безопасные DTO.
2. Сохранение, изменение и очистка draft, возврат на предыдущую позицию; skip/advance.
3. Ручное завершение, все пропуски, результат и порционный review после завершения.
4. Истечение времени до запроса и непосредственно во время INSERT draft; сохранённые
   ранее ответы остаются, поздний ответ не включается, timeout коммитится.
5. Resume через attempt/active/result, фиксированный deadline без продления срока.
6. Справочные ключи недоступны до окончания Exam; чужие попытки/результаты/review — 404.
7. Потерянный HTTP-ответ и same-key replay, в том числе после общего cache TTL
   и окончательного finish: исходная active-проекция не начинает раскрывать feedback.
8. Отзыв контента во время Exam; исходные snapshot IDs/ключи сохранены.
9. Реальные независимые PostgreSQL транзакции: concurrent start/draft/edit,
   finish↔два finalizer; одна версия/один результат, без удвоения response.
10. Новый экземпляр API с новым pool читает сохранённые ответы; закрытый клиент
    не нужен worker для финализации. Синтетический crash до commit откатывает всё;
    повторный запуск worker завершает ровно один раз.
11. PostgreSQL запрещает изменение terminal результата, deadline, draft и snapshot.
12. Learning regression, совместимость 0008 canonical hash и сохранённой истории.

Тесты используют синтетический банк и отдельные одноразовые БД. Реальный Telegram,
TCP disconnect, kill процесса во время commit и испытания на VPS не проводились;
потеря ответа/новый API instance/crash до commit моделируются автоматическими тестами.

## Изменённые файлы

- `backend/app/attempts/models.py`, `schemas.py`, `service.py`, `api.py`.
- `backend/app/attempts/exam.py`, `finalizer.py`.
- `backend/app/content/api.py` — reference lock в активном Exam.
- `backend/migrations/versions/0009_exam_attempts.py`.
- `backend/app/db/schema.py`.
- `backend/tests/test_exam_attempts.py`, `test_exam_concurrency.py`, `test_exam_migrations.py`.
- `backend/tests/test_learning_attempts.py` — устаревшее ожидание неподдерживаемого
  mode=exam заменено на действительно неподдерживаемый mode; Learning-сценарии сохранены.
- `backend/tests/test_import_migrations.py`, `test_publication_policy.py` — новая schema head.
- `backend/scripts/runtime_smoke.py`, `exam_runtime_smoke.py`.
- `backend/compose.dev.yaml`, `README.md`, `EXAM.md`, `EXAM_REPORT.md`.
- `docs/MEDEXA_BACKEND_ARCHITECTURE.md`.
- `.github/workflows/medexa-backend.yml`.

## Ограничения и следующий этап

- Только single_choice, regular, ordered_all v1, до 5000 вопросов. Multi-choice,
  random policy и набор нескольких test_definition IDs одним start не добавлены.
- До будущего развёртывания требуется постоянно работающий finalizer. При его
  остановке API остаётся способен финализировать просроченный Exam при обращении;
  background-материализация возобновится после восстановления worker/БД.
- Сервер сохраняет принятые ответы. Не переданные из offline-клиента данные не могут
  быть восстановлены сервером; не принимаются задним числом после deadline.
- Reference lock не является прокторингом и не отзывает ранее скачанные материалы.
- Deadline-policy topic/discipline нужно утвердить как продуктовую перед React-интеграцией.
- Отдельно нужны нагрузочный gate 1 CPU/2 GB, backup/retention и реальные iOS cookies/
  reopen проверки. XP, профильная история/статистика, Premium и платежи не реализованы.

Frontend, main, Preview, Production, старый Backend и действующие базы не менялись.
Merge/deploy не выполнялись. Проверки и image запускались только в изолированном
локальном окружении; работающих серверов задачи не касаются.

## Откат

Предпочтителен forward fix. При отсутствии Exam-истории 0009 допускает возврат к 0008,
сохраняя Learning. При наличии Exam-истории downgrade намеренно блокируется.
Не удалять историю ради rollback. Не запускать старое API со schema head 0009;
при будущем развёртывании согласовать backup и остановку finalizer отдельно.
