# MEDEXA Backend 2.0 — этап 5

Ветка: `feature/medexa-progress-statistics`.
Основа: `3e04c071b1a7f0c3b8c80827b2d2ead8b70edfb0`.
База Draft PR: `feature/medexa-exam-attempts`.

## Результат

Реализованы собственная история Learning/Exam с фильтрами и keyset-пагинацией,
сводка для Home/Profile, прогресс по дисциплинам и темам, календарь/недельная
активность/динамика, ошибки, рекомендации и четыре вычислимых достижения.
Исторические ответы просматриваются порциями по исходным revisions/options,
без раскрытия активных Exam ключей через новые API.

Источник — неизменяемые завершённые attempts/responses текущего progress_epoch.
Abandoned и in_progress не считаются завершениями. Нет второй истории, дублирующего
score, накопительных счётчиков и обработчика начислений: replay/restart/concurrent
finish не удваивают статистику. Нет XP, платежей, нового worker или зависимостей.

[Контракты API, формулы, временные зоны и эксплуатация](PROGRESS.md).

## Миграция 0010

- Частичный индекс `(user_id, progress_epoch, finalized_at DESC, id DESC)` для completed history.
- Nullable `attempt_items.topic_id`: будущие sealed snapshots фиксируют реальную тему,
  включая каноническое первое вхождение вопроса в дисциплине. FK и INSERT guard;
  существующий immutable guard сохраняет запрет правки snapshot.
- Маленькая immutable `daily_recommendations` с PK(user_id, local_date), FK и guards;
  дневной выбор остаётся стабильным, отсутствие материалов не подменяется вымыслом.
- Legacy topic/test используют достоверный fallback attempt.topic_id. Неоднозначные
  старые discipline ответы учитываются в общей статистике, но не угадываются по
  текущему каталогу; доступны через unattributed_topic_responses.
- 0001–0009 не изменены. Готовность API/finalizer проверяет новую schema head.

## Проверки

| Проверка | Результат |
|---|---|
| Полный `scripts/check.sh`, Python 3.12.14, PostgreSQL 16.16 | **349 passed, 142.25 s** |
| Ruff check/format | Успешно, включая отдельный runtime smoke script |
| Strict mypy | Успешно, 72 app modules |
| Fresh/repeat upgrade, downgrade/upgrade, Alembic schema drift | Успешно, no new upgrade operations |
| Сохранённые Learning-ответы, replay, старые миграции | Успешно; legacy snapshot не требует угадывания topic |
| Docker runtime build | Успешно, frozen deps, non-root, TLS verification включена |
| Runtime `/live`, `/ready`, PG16/schema 0010/finalizer poll | Успешно, реальный loopback HTTP внутри образа |
| Runtime HTTPS auth + 11 progress routes | Успешно, проверенный временный TLS certificate, настоящая HMAC-проверка синтетического initData, Secure cookie jar |
| Runtime parser smoke, network none | Успешно, count=1, elapsed=4ms, parser max_rss=87256 KiB |
| Изолированные Compose dev/test config | Успешно |
| CI | Полный PG16/Pytest/Ruff/mypy/migrations/build/runtime gate включён для новой ветки; окончательный статус — checks Draft PR |
| Scope diff | Только новый backend, его docs/workflow; Frontend и 0001–0009 не менялись |

Проверенные новые сценарии:

1. Пустая история: известные counts=0, неизвестное среднее/время=null, отсутствие
   фиктивного избранного/достижений/рекомендаций; Home не содержит несуществующий active.
2. Learning и Exam, все пропуски, active Exam с 100 сохранёнными выборами,
   abandon после проверенного ответа — метрики только после completed.
3. История из **102** завершений без лимита общей истории в 100; keyset без дубликатов,
   фильтры по mode/topic, подмена cursor/владельца/epoch отклоняется.
4. Ownership, включая другого admin: чужие result/result-review — 404, own history
   и statistics не раскрывают чужие строки, user_id не меняет владельца SQL.
5. Result-review порциями all/incorrect/skipped, исходные options/revisions, нейтральные
   пропуски; активный Exam закрывает новый справочный разбор.
6. Numeric average: 1/6 и 1/2 дают **33%**, включая групповой прогресс.
7. Ошибка → правильный ответ → skip: ever_wrong остаётся, unresolved снимается
   правильным, skip не создаёт и не стирает ошибку.
8. IANA DST (весна/осень), полночь и понедельник; PostgreSQL date совпадает с ZoneInfo;
   смена текущей timezone не переносит дату сохранённого результата.
9. SQL streak islands: несколько завершений за один день не увеличивают серию,
   три последовательных даты распознаются, устаревшая current streak=0 при сохранённой longest=3.
10. Сто реальных тестовых серверных ответов дают first/hundred/perfect; остальные
    ненастроенные условия не разблокируются и XP не начисляется.
11. Daily-topic сохраняется при изменении истории, withdrawn возвращается без подмены;
    empty остаётся empty до следующего календарного дня.
12. Реальные независимые PG-транзакции: повторные finish и finish↔timeout↔Home
    дают ровно один вклад. Новый API instance/pool читает те же реальные показатели.
13. Изменение topic_questions после старта не переписывает тему snapshot;
    legacy discipline без достоверной темы отмечается как unattributed.
14. Downgrade блокируется при угрозе потери attribution; общий roundtrip пустой схемы
    и прежние Learning/Exam regression tests проходят.

Все вопросы/пользователи в новых тестах и runtime smoke синтетические и хранятся
только в одноразовой test БД. Runtime smoke разрешает только environment=test и
medexa_foundation_test. Для HTTPS используются временные ключ/сертификат в приватном
tmpfs; certificate verification и обычная HTTPS-защита приложения остаются включены.
Нет обходного auth endpoint или фиктивной Production-авторизации.

## Изменённые файлы

- `backend/app/progress/__init__.py`, `models.py`, `schemas.py`, `service.py`, `api.py`.
- `backend/app/attempts/models.py`, `service.py` — индекс и snapshot attribution,
  без изменения правил ответа, deadline, результатов и действий Learning/Exam.
- `backend/app/identity/policy.py`, `app/main.py` — собственное разрешение и router.
- `backend/migrations/versions/0010_progress_statistics.py`, `migrations/env.py`,
  `app/db/schema.py`.
- `backend/tests/test_progress_api.py`, `test_progress_precision.py`,
  `test_progress_attribution.py`, `test_progress_concurrency.py`.
- `backend/tests/conftest.py`, `test_exam_migrations.py`, `test_import_migrations.py`,
  `test_publication_policy.py` — metadata/head и моделирование legacy snapshot.
- `backend/scripts/runtime_smoke.py`, `exam_runtime_smoke.py`, `progress_runtime_smoke.py`.
- `backend/README.md`, `PROGRESS.md`, `PROGRESS_REPORT.md`.
- `docs/MEDEXA_BACKEND_ARCHITECTURE.md`, `.github/workflows/medexa-backend.yml`.

## Ограничения

- Старые discipline attempts без item-topic attribution нельзя достоверно разбить
  по темам; это обозначено явно, общие итоги при этом сохраняются.
- Календарь использует сохранённую IANA-зону старта попытки. Смена зоны в середине
  попытки не меняет её календарную политику; при путешествиях даты могут расходиться
  с текущим локальным «сегодня». Исторические даты не переносятся.
- Practice time — серверная wall-clock длительность, не измерение активного экрана.
- Групповой прогресс описывает наблюдавшиеся вопросы/завершения, не выдуманную долю
  освоения всего текущего каталога.
- Рекомендации — документированная ограниченная эвристика v1: до 100 слабейших
  исторических кандидатов, затем проверка доступности; не медицинская оценка.
- Достижения вычисляются без ledger и даты выдачи. Пять условий не настроены;
  XP, уровни, постоянные awards, favorites, error-repeat/reset API не добавлены.
- Нет гарантии фиксированного SQL snapshot между страницами живой истории.
- Полная нагрузка/RAM на VPS 1 CPU/2 GB и реальный Telegram iOS не проверялись.
  Приведённый parser max_rss не является RAM API/статистики/VPS. При большой истории
  query timeout может вернуть 503; дальнейший кеш/проекции — по результатам измерений.
- React-интеграция, серверные уведомления и публикация в работающем окружении —
  отдельные этапы. Дизайн и Frontend не изменялись.

## Откат

Предпочтителен forward fix с backup. Пустую 0010 можно откатить к 0009; при наличии
новых item-topic или daily rows downgrade намеренно блокируется. Не отключать guards
и не удалять историю ради rollback. Не запускать старый API против новой schema head.

Main, Preview, Production, старый Backend и действующие базы не менялись.
Merge/deploy не выполнялись; все контейнеры/HTTPS-серверы запускались только как
изолированные локальные проверки и завершались после smoke.
