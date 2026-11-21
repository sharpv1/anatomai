# Явная публикация вопросов — этап 3b.3

Основа: `d5a22d1c092947966485fe04e5a4a71e2ed2f9ca`, миграция `0007_publishing`.
Загрузка по-прежнему создаёт только draft. Источник, лицензия и второй reviewer
не являются условием публикации. Административный Frontend не добавлен.

## Доступ и обязательное подтверждение

Все URL ниже начинаются с `/api/v1/admin`. Сохраняются HTTPS, Origin,
HttpOnly-сессия, CSRF для мутаций и свежая серверная MFA (существующий step-up).

- Editor (`content_editor`): отдельные **собственные** редакции.
- Admin: отдельные доступные редакции и подтверждение наборов импорта.
- Reviewer не заменяет editor/admin и не получает новые HTTP-права публикации.
- Student/support/billing не имеют доступа. Чужая редакция редактору — 404.

У каждой новой команды publish/withdraw/restore/import publish обязательны:
`Idempotency-Key: <UUID>`, `If-Match: <ETag предпросмотра>`,
`confirm: true` (именно JSON boolean) и `preview_hash` из предпросмотра.
Нет автоматической публикации после upload, successful parse или обычного GET.

## Отдельная редакция

`GET /question-revisions/{id}/publication-preview` возвращает Envelope с
`preview_hash`, `state`, `publishable` и ETag. Снимок содержит actual body hash,
raw content/options hash, option IDs, current pointer, номер последней редакции,
связи и состояния родителей. Stored fingerprint не считается доказательством
неизменности: сервер перечитывает реальные тексты/варианты и проверяет структуру.

`POST /question-revisions/{id}/publish`:

```json
{"confirm": true, "preview_hash": "<64 hex из предпросмотра>"}
```

Публикуется актуальный draft single_choice: 2–8 непустых вариантов, ровно один
правильный, допустимые размеры/коды; question не архивирован, связи с темами есть,
родители не withdrawn. Старую неактуальную draft нельзя молча активировать.
Повтор уже активной опубликованной редакции возвращает unchanged.

`POST /question-revisions/{id}/withdraw` и `.../restore` дополнительно требуют
`reason` (непустой текст до 512 символов; не помещать туда секреты/данные пациентов).

Withdraw переводит только published → withdrawn; pointer очищает существующий
DB trigger, только если он указывал на отозванную редакцию. Более новая активная
редакция не снимается случайно при отзыве старой. Текст/варианты не переписываются.

Restore имеет две семантики:

1. Ранее опубликованная, ещё published редакция: вернуть current pointer на неё.
2. Withdrawn редакция: она остаётся withdrawn навсегда. Создать **новую** опубликованную
   редакцию-копию с новым revision number и новыми option IDs; source revision ID
   и причина записываются в audit. Старые записи и будущие ссылки attempts не меняются.

Если эквивалентная копия уже активна, повтор restore — unchanged. Никакого fictitious
self-review: medical_review_by/reviewed_at не заполняются ради публикации.

Ответ мутации: revision_id, question_id, outcome и catalog_version. Это результат
команды, не обещание, что pointer никогда не изменится последующими действиями.

## Импорт: предпросмотр → выбор → подтверждение

1. Дождитесь `completed` import job (см. [IMPORTS.md](IMPORTS.md)).
2. `GET /imports/{id}/publication-preview` (admin) возвращает:
   - found/valid/errors/duplicates/conflicts/publishable;
   - eligible_positions и blocked с координатами и кодами причин;
   - hidden_parent_count, SHA-256 файла, template_version, result_version;
   - preview_hash/staging_hash и ETag; история предыдущих run тоже входит в preview hash.
3. `POST /imports/{id}/publish`, заголовки выше, body:

```json
{
  "confirm": true,
  "preview_hash": "<из текущего предпросмотра>",
  "file_sha256": "<из текущего предпросмотра>",
  "template_version": 1,
  "selected_positions": [1, 2, 5]
}
```

Выбор обязателен и явный; 1–5000 уникальных позиций, одна редакция каждого question.
Список числовых позиций помещается в существующий 32 KiB JSON limit даже для 5000 строк.
Каждая выбранная строка должна быть publishable; duplicate/conflict/error/multiple_choice,
неактуальная или изменённая редакция отвергают **всё подтверждение**.

Можно явно выбрать корректную часть набора, оставив ошибки/дубликаты вне выбора:
они не публикуются, `excluded` отражён в результате/audit. Это уточнение прежнего
плана «ошибка блокирует весь набор»: ошибочные **выбранные** строки всегда блокируют
команду; невыбранные строки не пропускаются молча, они видны в предпросмотре/отчёте.

Ответ 200 означает принятую команду: publication_id, status=queued, selected/excluded.
Он не означает завершённую публикацию. Worker не хранит OTP/initData/session token;
в run — actor/session UUID, время подтверждённой MFA и immutable снимки.

Проверяются фактический файл в private store (SHA и размер), template/result version,
**все** staging rows, их normalized payload, stored fingerprint и реальные revisions.
Файл должен ещё храниться. После raw TTL остаётся отдельная публикация редакции
по её собственному явному предпросмотру, без имитации сохранённого исходного файла.

После подтверждения import rows и содержательные metadata job/asset замораживаются
DB triggers; повторный import retry этого job запрещён. Исправления — новая загрузка
или новая редакция через существующий draft API, затем новое подтверждение.
Редактирование draft после подтверждения не публикует новые данные по старому согласию:
worker сравнит полный снимок и остановится.

## Обработка и отчёты

`GET /publications/{id}` (admin) возвращает status, attempts, cancel_requested,
error_code/message, current_catalog_version, counts pending/published/unchanged/failed
и выбранные items (position/revision_id/status/error_code). Размер ограничен 5000 items.
Items — неизменяемые итоги команды; последующий withdraw не переписывает их.
Это отдельный JSON-отчёт публикации; исходный CSV импорта сохраняется без подмены смысла.

Worker фиксирует атомарные batch **не более 100**: сначала проверяет весь batch,
затем изменяет status/pointers, audit и item outcomes в одной транзакции.
Deferred structural/pointer DB guards выполняются внутри batch. Уже опубликованные
items никогда не исполняются заново. Большой набор **не** all-or-nothing.

Каждый batch повторно проверяет права/активность подтвердившего admin, фактический
файл, staging, выбранные позиции и полные снимки неприменённых редакций. Публикация
своих материалов разрешена; source/license/reviewer gate не возникает скрыто.

`POST /publications/{id}/cancel`: queued отменяется сразу, processing — на ближайшей
границе batch; опубликованное сохраняется. Повтор cancel безопасен.

`POST /publications/{id}/retry`: admin с новой актуальной MFA/CSRF; failed/cancelled,
не более 3 запусков, исходник/staging прежние. Продолжает pending после transient failure
или отмены. STALE_ITEM/STAGING_CHANGED/FILE_CHANGED/ACCESS_REVOKED требуют нового
предпросмотра и явного решения, а не автоматического изменения согласия.
При наличии более нового run того же импорта старый run повторить нельзя.
После исчерпания трёх попыток можно получить новый предпросмотр и явно подтвердить
новый run; история старого сохраняется, применённые вопросы становятся unchanged.

После crash lease 120 s освобождается для reclaim; token fencing и общий advisory lock
останавливают старый worker. Завершённые batch сохранены, незакоммиченный batch откатан.
Есть общий срок job 600 s и max attempts=3. MFA/session expiry после принятия команды
сама по себе её не отменяет; блокировка admin/отзыв роли останавливают pending.
Для немедленной остановки используйте cancel или блокировку пользователя.

## Идемпотентность и конкуренция

Foundation Idempotency-Key scope — actor/operation/key, canonical resource+body hash.
Повтор с тем же ключом/телом возвращает исходный результат **до** проверки свежего ETag:
действие не исполняется повторно. Другой payload с тем же ключом — 409.

Новая publication_commands — постоянная immutable business receipt. Даже после
истечения/очистки 7-дневного общего idempotency cache restore не создаст лишнюю копию,
а import publish не поставит второе задание. Отдельно защищают:
UNIQUE(job,confirmation_hash), partial UNIQUE active run/job, UNIQUE(run,question),
immutable selection hash/count и постоянные outcomes items.

Lock order: identity → catalog → import/run → content. Global catalog singleton
сериализует разрешённые content writes; новый неподтверждённый ETag даёт 412.
Два admin не смогут подтвердить один job одновременно; действующий run даёт 409.
Нет авто-merge, автоматического перезаписывания новой редакции старой или «последний wins».

Изменения status/pointer используют существующие content triggers: catalog_version
монотонно увеличивается, старые signed cursors дают 409 CATALOG_CHANGED, ответы no-store.
Кеши Frontend не менялись. После завершения команды клиент должен перечитать данные.

## Dev worker, миграция и эксплуатация

`0007_publishing` добавляет publication_commands/runs/items, FK/UNIQUE/index/guards.
0001–0006 не переписаны. Старый immutable guard не ослаблен для restore.
Nullable session FK могут обнулиться при штатном Identity retention, не стирая команду.

В существующем **dev** Compose сервис import-worker теперь исполняет
`python -m app.publishing.worker --with-imports`: один процесс/pool=2 на обе очереди,
последовательно по одному заданию каждой очереди. Общий singleton lock совместим
с прежним import-only CLI и защищает от случайного запуска двух процессов.

```sh
# Только изолированная dev/test среда после настройки private env и явного backup:
docker compose -f compose.dev.yaml --profile tools run --rm migrate
docker compose -f compose.dev.yaml --profile imports up -d api import-worker
```

Нативно: `uv run python -m app.publishing.worker --with-imports`;
только publication queue: без --with-imports; --once — одно доступное задание.
Это инструкция, не выполненный deploy. Production-конфигурации здесь нет.

Raw cleanup исключает queued/processing публикации; после остановки terminal run
прежний TTL действует. История команд/снимков/отчётов сохраняется, без автоудаления.
Audit фиксирует confirmer, выбранное/исключённое количество, переходы/причины/source
revision, каждый опубликованный item и финал run. Worker correlation ID — run UUID;
подтверждение связывает его с исходным HTTP request ID. В логи попадают только event,
job UUID, status/code — без медицинского текста, cookies и ключей.

## Ограничения и следующий этап

- Только single_choice; multiple_choice остаётся draft, без изменения текущего клиента.
- Metadata дисциплин/тем не публикуются неявно. Если родители draft, вопрос может быть
  published, но не виден в каталоге: это явно отмечает hidden_parent_count/state.
  Нужны существующие связи и неотозванные родители; новые orphan drafts требуют темы.
- Реального движка attempts пока нет. Защищены существующие revision/option IDs;
  следующий этап должен snapshot-ить их сервером, а не читать только current pointer.
- Импортный preview может быть большим; нет гарантий throughput на VPS без нагрузочного
  gate. Проверены реальные 205-item batches и конкурентные транзакции PostgreSQL 16.
- Нет XP/Premium/Stars/оплаты/административного Frontend или изменений React.

Предпочтителен forward fix. Downgrade 0007→0006 разрешён только при отсутствии
publication receipts/runs: история подтверждений не удаляется ради отката.
Откат кода и схемы согласовывается отдельно; не откатывать схему под новым runtime.
