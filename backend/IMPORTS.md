# Массовый импорт, этап 3b.2

Основа: `d190b9d00d7f33ceeb16d91878685085c580a491`, политика 0005.
Импорт сохраняет **только черновики**. Источник, лицензия, страница, объяснение
и второй рецензент не обязательны. HTTP-публикация остаётся закрытой до 3b.3.
Frontend и административный веб-интерфейс этим этапом не добавляются.

## Простой шаблон v1

Получите `GET /api/v1/admin/import-templates/xlsx` или `.../docx` с действующей
staff-сессией и MFA. Файлы содержат только заголовки, без вымышленных вопросов.
Заполняйте один лист XLSX либо таблицы DOCX с одинаковыми заголовками в каждой таблице.
Текст вне таблиц DOCX не задаёт параметры импорта. Вложенные/объединённые ячейки,
изображения, вложения, track changes, поля Word и внешние связи не поддерживаются.

Обязательные колонки (русское имя / каноническое имя):

| Колонка | Значение |
|---|---|
| Дисциплина / discipline | Точное название или slug существующей дисциплины |
| Тема / topic | Точное название или slug темы в этой дисциплине |
| Вопрос / question | Непустой текст, до 8000 байт UTF-8 |
| Ответ A / option_A | Первый вариант, до 2000 байт UTF-8 |
| Ответ B / option_B | Второй вариант, до 2000 байт UTF-8 |
| Правильный ответ / correct | Явная латинская буква A–H; для нескольких — `A;C` |

Дополнительные колонки: `option_C`…`option_H` (также «Ответ C»…«Ответ H»),
`external_id` («Внешний ID»), `kind` («Тип»), `source_reference` («Источник»),
`license_reference` («Лицензия»), `source_page` («Страница»),
`explanation` («Объяснение»), `source_id` (UUID).
Пропущенные/пустые метаданные становятся null, без предупреждений о лицензии.
`kind` по умолчанию `single_choice`; несколько правильных требуют `multiple_choice`.
Такие вопросы можно сохранить в draft, но текущий public/test контракт и DB publication
trigger поддерживают только single_choice. Правильные ответы не угадываются по оформлению.

Дисциплины/темы создаются заранее через существующий draft API. Импорт не создаёт
родителей автоматически и не открывает draft-каталог студентам. При неоднозначном
названии используйте slug. Переданный source_id должен существовать и быть доступен
автору (либо admin); сам источник совершенно необязателен.

## API и последовательность

Все пути ниже требуют `content.import.manage`: `content_editor` или `admin`,
действующая серверная сессия и свежий MFA grant; изменяющие запросы — Origin и CSRF.
Reviewer не получает разрешение на импорт автоматически. Обычный вход не даёт MFA.

1. `POST /api/v1/admin/imports?format=xlsx` (либо docx): **сырой бинарный body**,
   Office MIME или application/octet-stream, не multipart/JSON. Возвращает 201 + queued
   job. Одно действие загружает файл и ставит задание в очередь; второго подтверждения нет.
   Тот же SHA-256/формат/шаблон у того же автора возвращает тот же job, 200, reused=true.
2. `GET /api/v1/admin/imports?limit=20&cursor=...`: свои задания; admin видит все.
3. `GET /api/v1/admin/imports/{id}`: queued/processing/completed/failed/cancelled,
   phase, found/valid/errors/possible_duplicates/drafts_created, error_code/message.
   completed может содержать ошибки отдельных строк. `publication_available=false` всегда.
4. `GET .../{id}/rows?limit=30&cursor=...`: после остановки/завершения, до 100 строк
   на страницу. Координата `sheet:row:N` или `table:N:row:M`, action,
   короткий текст вопроса, `errors/warnings: [{code,message}]`, draft_revision_id.
   `create/update` — новая draft revision; `unchanged/duplicate` — без новой копии;
   `error/conflict` — строка не применена. Отчёт не раскрывает чужие private draft ID.
5. `GET .../{id}/report`: CSV с UTF-8 BOM, координатами и понятными ошибками;
   значения экранированы против Excel formula injection. Raw-файлы не скачиваются.
6. `POST .../{id}/cancel`: queued отменяется сразу; processing останавливается
   на ближайшей проверке/границе batch. Уже закоммиченные draft остаются и учтены.
7. `POST .../{id}/retry`: failed/cancelled или completed с ошибками, не более трёх
   запусков суммарно и пока raw сохранён. Повтор не дублирует применённые revisions.
   Старый cursor строк после retry даёт 409; сбой/отмена не означают rollback всего файла.

Для rows/report в queued/processing возвращается 409 IMPORT_PROCESSING; счётчики
доступны через detail. Чужой job редактору — 404. Нет URL raw/quarantine и HTTP publish.
Все ответы используют существующий Envelope/error contract и no-store.
Секреты берите из существующей процедуры входа/MFA, не подставляйте в shell history.

## Идентичность и версии

Namespace — `import-topic:<topic UUID>`, не библиографический источник.
Без external_id создаётся `auto:<sha256>` нормализованных kind/text/вариантов;
позиция строки и формат файла не участвуют. Исправление ключа/объяснения/метаданных
сохраняет этот ID и создаёт новую draft revision, если fingerprint изменился.
Изменение текста/вариантов без external_id означает новый вопрос: для стабильного
редактирования экспортируйте/ведите собственный внешний ID (до 124 символов).

Есть второй индекс точного content hash (включая ответ): повтор импортированного
содержимого в той же теме под другим ID пропускается. Он сохраняет исторические
хэши импорта. Похожий текст в существующем банке — предупреждение, без эвристического
слияния медицинских вопросов. Два разных содержимых с одним ID в одном файле
дают conflict для всех соответствующих неприменённых строк. Данные другого редактора
не перезаписываются. Изменения всегда создают **новую** draft, не изменяют старые
published/withdrawn revisions, options или current_revision_id.

## Запуск и ограничения

Нужна миграция `0006_import_staging` и приватный абсолютный каталог
`MEDEXA_IMPORT_STORAGE_DIR` (владелец процесса, права 0700, файлы 0600).
Пустая настройка отключает upload с 503. Каталог запрещено размещать в app/public
или дереве исходников; API и worker разделяют только отдельный закрытый volume.
Исходное имя файла не сохраняется; storage key — серверный UUID, не пользовательский путь.

Для **изолированной разработки** после настройки секретов и явной миграции:

```sh
docker compose -f compose.dev.yaml --profile tools run --rm migrate
docker compose -f compose.dev.yaml --profile imports up -d api import-worker
```

Нативно: `uv run python -m app.imports.worker` (либо `--once`). Один worker на БД:
сессионный advisory lock + SKIP LOCKED, lease 120 s, token fencing, максимум 3 запуска.
Worker использует pool_size=2: отдельное соединение singleton-lock и одно для транзакций.
Actor status/права проверяются перед каждым batch. Истечение обычной сессии/MFA после
приёма команды не отменяет уже разрешённое задание; блокировка/отзыв роли останавливают
неприменённую часть. В job хранятся UUID сессии/время MFA, без session token/OTP/initData.

Ограничения: файл 10 MiB, распакованное содержимое 50 MiB, часть 10 MiB,
2048 ZIP entries, central directory 512 KiB, 1 млн XML nodes, 5000 вопросов,
строка/JSON до 64 KiB, вывод парсера 64 MiB, загрузка 60 s, парсер 60 s wall/CPU,
общий job 600 s. Не более 3 активных заданий/автора, raw quota 100 MiB/автора,
проверка свободных 256 MiB перед загрузкой. Batch — до 100 вопросов, атомарный с audit.
Размер сжатого файла не является оценкой будущего размера PostgreSQL; нужны мониторинг
диска/WAL и операторское обслуживание staging, особенно при больших медицинских текстах.

В HTTP нет ZIP/XML парсинга. Отдельный child получает только file paths/hash/format,
без DB/Telegram/MFA env, не извлекает ZIP и не загружает внешние URL.
Проверяются SHA, OPC/MIME, пути/симлинки/дубликаты, ZIP ratio, DTD/entities,
формулы даже с cached value, макросы, встроенные объекты и внешние relationships.
Действуют RLIMIT_AS=256 MiB, CPU=60 s, FSIZE=64 MiB, NOFILE=32.
Это **не** отдельная VM и не filesystem/network namespace; worker-контейнер
non-root, read-only, cap_drop ALL, no-new-privileges, отдельная сеть/volume.
Compose RAM 512 MiB/CPU 0.5 — параметры для совместимого Docker host, не замена измерения.

Ежедневное операторское обслуживание: `uv run python -m app.imports.cleanup`.
Команда берёт тот же singleton-lock, удаляет raw terminal jobs старше 30 дней
(до 100 за запуск), work/orphan files старше 24 часов (осмотр до 10000 entries).
Не удаляет draft/questions, отчёты и audit. Если worker занят — повторить позже.
Raw TTL относится только к файлам; normalized staging/reports пока сохраняются для
3b.3 и аудита. Согласованный архив/удаление staging — отдельная операционная задача.

## Откат

Остановить dev worker/API; backup БД и приватного volume; предпочтителен forward fix.
`0006 -> 0005` удаляет staging/jobs/dedup и nullable license_reference, **не удаляет**
созданные draft-вопросы. При license metadata в immutable history downgrade заранее
отказывается от потери истории. Нельзя откатывать схему под работающим новым runtime.
Здесь миграции выполняются только на одноразовой тестовой БД, не на VPS/Preview.
