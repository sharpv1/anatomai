# MEDEXA Exam Engine — этап 4b

Основа: `1a598f4425ad9497f6fb60b6a999266816cc2b21`; новая head:
`0009_exam_attempts`. Learning API и его locked submit/advance/skip/finish/abandon
сохраняют прежнее поведение. Frontend не подключён.

## Старт и политика v1

`POST /api/v1/attempts`, сессия, CSRF/Origin, `Idempotency-Key: UUID`:

```json
{"mode":"exam","topic_id":"<UUID>","question_count":20}
```

Вместо topic_id — discipline_id либо test_definition_id, ровно одно поле.
question_count необязателен, 1–5000; Learning его не принимает. Только доступные
published current single_choice. Порядок тот же, что в Learning: стабильный порядок
тем/вопросов, дедупликация question_id, без случайного перемешивания и повторов.
При явном count берутся первые N доступных вопросов. Если их недостаточно —
422 QUESTION_COUNT_UNAVAILABLE; сервер не дополняет и не повторяет вопросы.

Test definition: только ordered_all/policy_version=1; question_limit, если задан,
ограничивает доступный размер. Без count используется question_limit либо весь набор.
Превышение доступного банка или лимита определения — ошибка, не молчаливое изменение N.
Выбор нескольких test_definition_id за один start не введён: существующая модель
определяет scope одним тестом, темой или дисциплиной.

Длительность определения — существующее exam_duration_seconds (1–86400).
Для темы/дисциплины без определения действует явная **серверная политика v1**:
60 секунд на выбранный вопрос, максимум 86400 секунд. Это техническая начальная
политика, не медицинский норматив; изменение — отдельная версия политики.
Клиент не может прислать duration, deadline, результат, ключи или произвольный набор IDs.

Snapshot использует существующие immutable attempt_items/attempt_item_options и
оригинальные revision_id. Withdraw, публикация новой редакции и restore не меняют
вопросы, варианты, ключи и пояснения начатого экзамена. Сохраняется одна active/user
для обоих режимов. Start финализирует просроченный Exam перед созданием нового.

## DTO и время

Envelope содержит id/mode=exam/status/version/title/scope/IDs/total/current_position,
started_at/deadline_at/remaining_seconds/current_item. До завершения нет result,
is_correct, correct_option_ids, explanation или feedback. ExamItem — отдельный
allowlist: id/question_id/revision_id/position/text, safe options, state=draft и
selected_option_ids (ноль или один ID). Выбор не раскрывает правильность.

Время — PostgreSQL clock_timestamp, не timestamp клиента/процесса API.
remaining_seconds = ceil(max(deadline-now, 0)); это подсказка для UI, не разрешение
сохранить ответ. Срок не продлевается при resume, фоне, потере сети или рестарте API.
`completed` + finish_reason=timeout обозначает оконченный по времени экзамен;
нового terminal status, несовместимого с Learning, не добавлено.

GET `/attempts/{id}` — resume; `/me/active-attempt` — текущая попытка. Просроченная
попытка перед ответом финализируется. Первый active GET после timeout может вернуть
уже completed объект; последующие — null. GET `/attempts/{id}/result` — только completed.

## Команды

Все изменения требуют CSRF, UUID Idempotency-Key и **исходный** If-Match
`"attempt-<UUID>-<version>"`. Версия увеличивается на успешное изменение/финализацию.

| Метод и путь после /api/v1/attempts/{id} | Тело | Действие |
|---|---|---|
| PUT `/items/{item_id}/draft` | `{"selected_option_ids":["<option UUID>"]}` | Сохранить/заменить ответ любого snapshot item |
| PUT `/items/{item_id}/draft` | `{"selected_option_ids":[]}` | Очистить выбор до завершения |
| POST `/navigate` | `{"position":0}` | Перейти на любую позицию 0..total-1, включая предыдущую |
| POST `/advance` | `{"item_id":"<current item UUID>"}` | Следующий; на последнем окончательно завершить |
| POST `/skip` | такое же | Перейти дальше; не стирать уже сохранённый выбор |
| POST `/finish` | `{}` | Явно завершить по всем сохранённым ответам |
| POST `/abandon` | `{}` / `{"reason":"user_exit"}` | До deadline закрыть без результата |

Learning submit в Exam возвращает 422 EXAM_SUBMIT_FORBIDDEN. Learning draft/navigate
возвращают 422, без изменения версии. Для очистки уже выбранного ответа используется
явный draft [], а не skip. После completed/abandoned менять ответы нельзя.

## Результат и разбор

Финализатор один: сохранённые ExamAnswer превращаются в immutable AttemptResponse;
невыбранные вопросы становятся skipped. Сервер считает correct/wrong/skipped/answered,
ROUND_HALF_UP percent и wall-clock duration_seconds. Итог и responses фиксируются одной
транзакцией, без начислений XP. На timeout finalized_at **равен deadline_at**, даже
если worker восстановился позже; duration не включает задержку worker.

`GET /attempts/{id}/review?offset=0&limit=30` — только свой completed Exam,
limit 1–100. Возвращает snapshot-вопросы, все варианты, выбранный ответ,
correct_option_ids, is_correct (null для пропуска), существующее explanation.
До завершения/после abandon — 409 RESULT_NOT_AVAILABLE; чужой ID — 404.

На время активного Exam блокируется reference-questions и learning projection
контента для этого пользователя (409 EXAM_REFERENCE_LOCKED). После timeout чтение
сначала завершает экзамен. Это защита API от прямой утечки ключей, не прокторинг:
она не отзывает ранее скачанные материалы и доступ с другого аккаунта.

## Идемпотентность, сеть и гонки

Порядок блокировок: user → attempt → draft/response. Worker использует тот же порядок,
SKIP LOCKED на user, один экзамен/транзакция. CAS выполняется после replay-проверки.
Новый ключ со старым If-Match — 409; отсутствие If-Match — 412. При гонке edits ровно
один новый запрос с данной версией проходит. Finish и timeout создают один результат.

Ответ, сохранённый БД до deadline, переживает закрытие Telegram/перезапуск API.
При потере HTTP-ответа повторять тот же URL/key/body/**первоначальный If-Match**.
Историческая success-проекция возвращается без повторного изменения. Exam receipts
хранят компактную исходную выборку IDs/позицию/версию/таймер, потому что draft изменяем;
тексты и варианты для replay читаются из исходного snapshot, банк не дублируется; Learning compact receipts и canonical
hash старта сохранены совместимыми с 0008. Общий namespace learning.* оставлен ради
совместимости существующего cache, mode зафиксирован в fingerprint старта.
После replay необходимо GET resume: исторический remaining_seconds/ETag не является
текущим состоянием. Гарантия replay сохраняется после 7-дневного cache TTL.

Новый draft, пришедший после deadline, не принимается: при актуальном If-Match команда
возвращает 200 с окончательным timeout-результатом, чтобы финализация закоммитилась.
Если срок истёк непосредственно во время записи, DB-trigger отклоняет draft;
savepoint откатывает только этот draft, затем сохраняется timeout. Если worker уже
завершил попытку и версия изменилась — 409, затем GET. Никакой клиентский sent_at не
даёт продления срока. **Ответ, который клиент вообще не успел передать серверу,
сервер сохранить не может**; offline queue/индикация несохранённых ответов относятся
к будущей React-интеграции. Нет обещания принимать offline-ответы задним числом.

## Finalizer и эксплуатация

Новый небольшой процесс, тот же runtime image, без Redis/Celery:

```sh
python -m app.attempts.finalizer          # poll каждые 2 с, без busy loop
python -m app.attempts.finalizer --once   # одна попытка / smoke
```

Нужны отдельный рабочий DB pool и постоянный supervisor/restart policy в будущем
окружении. Readiness проверяет schema head 0009 и PG16. Ошибка итерации откатывает
транзакцию; следующий poll/перезапуск безопасно продолжает. Секреты/вопросы/выборы
в логи worker не пишутся. Индекс deadline только для active Exam.

Для **изолированного dev** добавлен Compose profile `exams`, mem_limit=192m:
`docker compose -f compose.dev.yaml --profile exams up --build` после явной миграции
по README. Автоматическое применение миграций при startup не добавлено.
Без запущенного worker API всё равно завершает просроченную попытку при чтении/команде,
но автоматическая материализация результата при закрытом клиенте требует worker.
Если API/БД/worker выключены, после восстановления результат фиксируется с исходным
deadline; физическую запись во время простоя инфраструктуры гарантировать невозможно.

Миграции 0001–0008 не изменены. 0009 расширяет mode, добавляет deadline и exam_answers,
FK/guard/индекс и условные Exam-ветки существующих guards. Published Content остаётся
immutable. Downgrade запрещён при наличии Exam-истории. Откат: резервная копия,
остановка finalizer и forward fix; не запускать API 4a против schema 0009.

Нет Exam-прокторинга, React-интеграции, статистики, XP, Premium, платежей или новых
зависимостей. Нагрузочный gate 1 CPU/2 GB и Telegram iOS остаются перед развёртыванием.
