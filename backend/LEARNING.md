# MEDEXA Backend — Learning Attempts, этап 4a

Основа: `f001e3e3a12d18f96182c87881ad3286ac039c96`; head — `0008_learning_attempts`.
Это серверное обучение без Exam, XP, статистических проекций и интеграции с React.

## Старт и snapshot

Все URL начинаются с `/api/v1`. Нужна действующая сессия пользователя, HTTPS,
Origin и CSRF для POST, как в Identity. Разрешение `attempts.self` не требует MFA;
admin также не может обращаться к чужой попытке через эти пользовательские API.

`POST /attempts` требует `Idempotency-Key: <UUID>`. Пример тела:

```json
{"mode": "learning", "topic_id": "<UUID темы>"}
```

Вместо topic_id можно указать discipline_id или test_definition_id — **ровно одно**
поле. kind=regular/mode=learning заданы по умолчанию; Exam/error-repeat не доступны.
При выборе test_definition разрешён только ordered_all/policy_version=1 без
question_limit. Ограниченные/другие политики отвергаются, не обрезаются молча.

Сервер выбирает только опубликованные доступные темы и current published single_choice
редакции. Unavailable policy, draft/withdrawn родители и архивированные вопросы не
попадают в набор. Пустой набор — 409 EMPTY_QUESTION_SET; максимум 5000 уникальных вопросов.
Дисциплина: порядок тем position/id, затем вопросов position/id; повтор одного question
в нескольких темах учитывается один раз, в первом доступном вхождении.

В одной транзакции фиксируются question_id/revision_id, порядок вопросов, все option_id
и их порядок, title, scope, catalog_version, timezone/progress_epoch и policy_version.
Варианты не перемешиваются. Тексты/ключи/объяснения читаются по исходной immutable
редакции, а не через текущий pointer. Контент не копируется в отдельный банк.
Публикация/withdraw/restore после старта не меняют этот snapshot.

Start удерживает catalog SHARE lock против публикационных изменений. Snapshot сначала
собирается, затем запечатывается; незапечатанную/неполную попытку нельзя закоммитить.
Таблицы snapshot после seal запрещают вставку, UPDATE, DELETE и TRUNCATE.

У пользователя одна активная попытка. Другой start — 409 ACTIVE_ATTEMPT_EXISTS с его
собственным attempt_id. Нужно resume либо явный abandon; незаметного сброса нет.

## Состояние и безопасные DTO

Start возвращает 201, Envelope с data/meta и ETag вида:
`"attempt-<UUID>-1"`. GET `/attempts/{id}` возвращает сохранённое состояние (resume).
GET `/me/active-attempt` возвращает активную попытку либо data=null.

В data: id/mode/status/version/title/scope, выбранные IDs, total/current_position,
started_at и current_item. Для terminal current_item=null; completed содержит result.
До завершения/после abandon result отсутствует, а не заполнен нулями.

current_item содержит id/question_id/revision_id/position/text/options и state:

- awaiting_answer: selected_option_ids=[], **нет** feedback, ключей или explanation;
- checked: один выбранный ID и feedback с is_correct/correct_option_ids;
  explanation присутствует только если исходная редакция её содержит.

Раздельные Pydantic DTO с extra=forbid и discriminated state не допускают feedback
в unanswered проекции. Options содержат только id/position/code/text. Ни клиентский
score/percent/duration, ни произвольные question IDs при старте не принимаются.
Справочный API остаётся самостоятельной функцией: Learning не является прокторингом.

## Команды

Каждый POST ниже требует CSRF, Idempotency-Key и **исходный** If-Match из полученного
состояния. Версия увеличивается ровно на 1 на успешно исполненную команду.

| Путь | Тело | Поведение |
|---|---|---|
| `/attempts/{id}/items/{item_id}/submit` | `{"selected_option_ids":["<UUID варианта>"]}` | Только текущий вопрос; фиксирует один ответ, возвращает checked/feedback |
| `/attempts/{id}/advance` | `{"item_id":"<UUID текущего item>"}` | Только после submit; следующий вопрос, на последнем — completed |
| `/attempts/{id}/skip` | `{"item_id":"<UUID текущего item>"}` | Только до submit; фиксирует skipped и продвигает, на последнем завершает |
| `/attempts/{id}/finish` | `{}` | Сохраняет проверенные ответы, весь неотвеченный хвост становится skipped |
| `/attempts/{id}/abandon` | `{"reason":"user_exit"}` или `{}` | Закрывает без результата; зафиксированные ответы остаются историческими фактами |

После submit ответ нельзя заменить, повторно submit/skip с новым ключом запрещён.
Один checked последний ответ сам по себе не завершает попытку: нужен advance или finish.
Нет Learning draft endpoint и не реализован Exam finalizer.

GET `/attempts/{id}/result` возвращает только собственный completed result;
для активной/abandoned попытки — 409 RESULT_NOT_AVAILABLE. Чужой/несуществующий ID — 404.
Перечня истории профиля `/me/attempts`, статистики и result-review в этом срезе нет.

## Оценка и время

Результат рассчитывает сервер из immutable attempt_responses:
correct, wrong, skipped, answered=correct+wrong, total=correct+wrong+skipped,
percent=ROUND_HALF_UP(correct*100/total), duration_seconds и timestamps/finish_reason.
Явные пропуски и непосещённый хвост — skipped, не wrong. Полностью пропущенный тест
имеет достоверные 0% и skipped=total. У abandoned нет завершённого результата.

Learning duration — wall-clock сервера/БД, включая паузы/фон/сеть, а не фиктивное
«время активного экрана». Клиентское время не принимается. Deadline/автоматического
idle expiry здесь нет: забытая попытка остаётся доступна для resume/abandon.

Межтабличные deferred guards проверяют seal, текущую позицию, версию ответа,
соответствие выбранного option snapshot-редакции, правильность server score и финальные
суммы/процент/длительность. Финальный результат и ответы нельзя переписать или удалить.
Не добавлены награды, XP, user progress, weekly activity или статистические агрегаты.

## Конкуренция, потеря ответа, restart

Lock order: identity user → attempt → response. Start дополнительно удерживает catalog
SHARE; mutating запросы не обращаются к текущему каталогу. Partial UNIQUE(user_id)
WHERE status=in_progress защищает единственную активную попытку на уровне PostgreSQL.

Foundation idempotency исполняется **до** проверки позиции/версии. Ответ успешного
повтора воспроизводит исходный результат, даже если попытка уже продвинулась.

Для повтора сохраняйте URL, key, body и исходный If-Match. Замена If-Match при том же
ключе меняет canonical request hash → 409 IDEMPOTENCY_KEY_REUSED. Новый ключ со старой
версией → 409 ATTEMPT_VERSION_CONFLICT; отсутствующий If-Match → 412.
Неверный текущий item →409; чужой option или два выбранных варианта →422.

Гарантия сохраняется после истечения общего 7-дневного cache: attempt_commands
хранит постоянную compact receipt (версия/статус/позиция/checked + hash), а исходная
проекция восстанавливается по immutable snapshot. Медицинский банк не дублируется
бессрочно в business receipts. Старый start остаётся старым start: для нового прохождения
нужен новый key. Общий idempotency cache имеет собственный expires_at; физическую
очистку просроченного cache согласовывать отдельно, не удаляя business receipts.

Resume и result читаются из PostgreSQL; в памяти API нет единственного источника
состояния. Сбой до commit откатывает ответ/версию/receipts вместе; потеря HTTP-ответа
после commit допускает безопасный повтор тем же ключом. Административное изменение
банка не изменяет сохранённую оценку старой попытки.

## Миграция, запуск, тестирование

0008 добавляет attempts, attempt_items, attempt_item_options, attempt_responses,
attempt_commands и их FK/индексы/guards. Ответ связан составными FK с item/attempt/
revision и с выбранным option той же snapshot-редакции. 0001–0007 не менялись.

Явный upgrade выполняется только в изолированной dev/test БД по существующему README.
Автомиграций при startup и новых worker процессов нет. Для обучения нужен API + PG16;
импорт/публикация используют существующий worker независимо от Learning.

Проверки: `uv run --no-sync sh scripts/check.sh` с изолированным environment=test,
MEDEXA_RUN_DB_TESTS=1 и medexa_foundation_test. Тестовая роль требует CREATEDB для
конкурентных тестов в отдельных одноразовых БД. Не использовать production credentials.
Подробные результаты: [LEARNING_REPORT.md](LEARNING_REPORT.md).

Предпочтителен forward fix: downgrade 0008→0007 отказывается удалять историю при
наличии attempts/commands. Не удалять ответы ради отката и не откатывать схему под
новым API. Backup/retention реального пользовательского прогресса должны быть
утверждены до будущего Production release.

## Следующий срез

4b: Exam draft/deadline/finalizer поверх того же snapshot, безопасные DTO без ответов,
server timeout/races finish↔deadline и отдельные тесты. Затем статистика/history,
награды и интеграция React — отдельные этапы. До развёртывания нужен нагрузочный gate
на 1 CPU/2 GB и реальная проверка Telegram iOS cookies/reopen; они здесь не проводились.
