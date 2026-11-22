# MEDEXA React integration — этап 6b

База: `51c7566feaea570e1d7f6f5ea3655dedea81b712` (6a).
Ветка: `feature/medexa-frontend-attempts-6b`.
PR направлен в `feature/medexa-frontend-integration-6a`.
Флаг `VITE_MEDEXA_BACKEND_ENABLED=false` остаётся значением по умолчанию.

## Реализация

- Из опубликованной темы запускаются Learning и Exam; опубликованные определения
  тестов запускаются с их собственным `test_definition_id` и серверной длительностью.
- Контроллер использует только серверный snapshot: UUID попытки, item/option IDs,
  версию, сохранённый выбор и разрешённую сервером обратную связь. Локальный банк,
  `useTestSession`, `resultSummary`, localStorage и импорт старых результатов в этой
  ветви исполнения не используются.
- Learning: немедленный серверный submit при выборе, зафиксированный ответ,
  правильность/существующее объяснение после сохранения, advance, skip и finish.
- Exam: PUT draft с сохранением/заменой/очисткой ответа, advance/skip, переход к
  предыдущим вопросам и finish. Показания таймера строятся от полученного
  `remaining_seconds` и монотонных часов. Только сервер может завершить попытку.
  GET при достижении нуля, восстановлении видимости и периодически сверяет состояние.
- При возврате из теста попытка **сохраняется активной**, не abandons автоматически.
  Главная предлагает продолжить через существующую кнопку; повторный запуск из
  каталога также возобновляет известную активную попытку. После полного открытия
  приложения используется `/me/active-attempt`. Одновременно разрешена одна попытка.
- Существующие файлы TestSession/TestResult содержат серверные представления с той
  же разметкой классов и CSS. Legacy функции оставлены без изменений. Ни один CSS,
  Telegram adapter/hook, шапка или нижняя навигация не изменены.
- Результат берётся из completed AttemptDTO: серверные percent/correct/wrong/skipped,
  duration и finish_reason, без локального пересчёта.
- Разбор completed Exam читает защищённый `/attempts/{id}/review` с offset/limit;
  Learning — `/attempts/{id}/result-review` с cursor/limit. До завершения компонент
  разбора не монтируется. Порции по 30, предыдущие ответы не заменяются каталогом.
- Home/Profile/Statistics повторно читают сервер при открытии после результата;
  счётчики не увеличиваются локально. Старые и серверные истории изолированы.

## Контракты и совместимость

Проверены `backend/LEARNING.md`, `EXAM.md`, `PROGRESS.md`, DTO и реальные API.
Используются существующие `/api/v1/attempts`, `/me/active-attempt`,
`/attempts/{id}`, `/items/{item_id}/submit`, `/items/{item_id}/draft`,
`/advance`, `/skip`, `/navigate`, `/finish` и защищённые review API.
Контроллер поддерживает также существующий abandon, но навигация назад не вызывает
его неявно. Новый маршрут, модель, миграция или движок не создавались.

Реальный E2E выявил оставшиеся заглушки этапа 3a: каталог всегда отдавал
`available_modes: []`, `/meta` сообщал `attempts: false`. В **новом** Backend
исправлена только выдача возможностей каталога:

- непустой доступный набор single_choice до 5000 вопросов темы — Learning/Exam;
- для определения учитываются ordered_all, policy_version=1, question_limit
  (Learning не принимает лимит) и допустимая длительность Exam;
- пустые и неподдерживаемые наборы не рекламируются как доступные;
- окончательная валидация и конкурентная фиксация остаются в существующем start API.

Схема остаётся `0010_progress_statistics`. Исторические записи не изменены.

## Ошибки и изоляция

Каждая мутация получает неизменяемый intent: URL, метод, сериализованное тело,
UUID Idempotency-Key и исходный If-Match `"attempt-<id>-<version>"` согласно контракту
ETag сервера. CSRF и cookie передаются существующим клиентом Identity.

Повтор после сетевой ошибки/таймаута отправляет **тот же** intent, а не новый ключ
и не обновлённую версию. Пока результат запроса неоднозначен, новые мутации
заблокированы; доступно явное повторение. После ответа, включая replay, выполняется
GET фактического состояния: idempotency receipt может содержать старую проекцию.
409/412 сверяют актуальную попытку; автоматической новой попытки нет. 401 запускает
существующее восстановление Identity, сохраняя intent в памяти того же владельца.

Контроллер живёт выше авторизационного экрана и привязан к подтверждённому user UUID.
При смене пользователя старый контроллер очищается; generation checks отбрасывают
запоздалые ответы. Cache/intent/результаты не пишутся в localStorage. Полная
перезагрузка восстанавливает только фактически сохранённое сервером состояние.
Неподтверждённые данные не объявляются сохранёнными; offline-очереди нет.

Runtime-валидация активного Exam отвергает feedback, correct_option_ids,
explanation, result и признаки правильности в вариантах. Правильность Learning
разрешена только в состоянии checked; итоги — только completed.

## Проверки

| Проверка | Результат |
| --- | --- |
| TypeScript | PASS |
| Frontend unit | 63 passed (10 новых сценариев attempts) |
| Production build, flag off / on | PASS / PASS |
| Chromium attempts | PASS: 375/390/430 px, включая 375×568, длинный вопрос/варианты, Learning/Exam, replay, 409, 401, offline, resume, смена аккаунта |
| Chromium read-only 6a regression | PASS: все три ширины, empty/error/retry/auth, Home/Profile/Statistics/каталог/конспекты |
| Default-off Home comparison | Byte-identical screenshots с исходной базой на 375/390/430 px |
| Legacy Learning/Exam UI | PASS: 9 width×browser/expanded/fullscreen, плюс 375×400 |
| Real HTTPS E2E + PostgreSQL 16 | PASS: HMAC/cookie/CSRF, Learning/Exam, resume, точный replay после потери реального ответа, protected review, worker timeout после закрытия страницы, Home statistics=3 |
| Full backend Pytest, PostgreSQL 16 | 357 passed; применены миграции до 0010, существующие migration tests проходят |
| Backend Ruff / format / mypy | PASS / PASS / PASS (72 source files) |

Реальный E2E и mock UI не смешиваются: отдельные JSON-отчёты и маркировка в
`docs/screenshots/frontend-6b/`. Начальный 401 `/auth/session` при первом входе
ожидаем; после HMAC-входа неожиданных API-ошибок в HTTPS E2E нет.

Команды:

```sh
npm run typecheck
npm test
npm run build
VITE_MEDEXA_BACKEND_ENABLED=true npm run build -- --outDir dist-backend
# Только loopback production preview: disabled 5180, enabled 5181, baseline 5182.
npm run test:attempts:ui
npm run test:backend:local
MEDEXA_SCREENSHOTS=/tmp/medexa6b-readonly-shots npm run test:backend:ui
# После cd backend && uv sync --locked; Docker с postgres:16-alpine.
backend/.venv/bin/python tests/run-attempts-https.py --check-backend
```

`run-attempts-https.py` создаёт собственный случайно названный контейнер PostgreSQL
16 (loopback, tmpfs, 256 MiB, отдельные credentials), применяет миграции, создаёт
синтетический published банк и поднимает FastAPI с TLS. Отдельный HTTPS frontend
proxy проверяет сертификат API. Chromium доверяет только в рамках тестового
контекста самоподписанному сертификату loopback (`ignoreHTTPSErrors`); приложение
и серверная HTTPS/Origin/CSRF-проверка не отключаются. После прогона процессы,
контейнер, БД и временные ключи удаляются. Чужая БД не принимается как параметр.

HMAC в E2E подписывается исключительно синтетическим test bot token. API не
подменяется. Подменяется только Telegram host SDK; cookie настоящая Secure/HttpOnly.
Проверяется реальная потеря HTTP-ответа **после commit** и replay с исходным key и
If-Match, Learning resume, Exam editing/resume/finish/review и deadline после
закрытия страницы. Прямой SQL read до следующего HTTP-запроса подтверждает работу
фонового finalizer, а не только lazy expiry на GET.

GitHub Actions выполняет обе сборки, frontend unit/UI, legacy regression и этот
реальный HTTPS E2E. Backend workflow запускает полный Pytest/Ruff/mypy/migrations.

## Скриншоты

`docs/screenshots/frontend-6b/`:

- learning/exam/result на 375, 390 и 430 px (mock transport, длинные формулировки);
- `https-learning-result-390.png`, `https-exam-review-390.png` — настоящий API/БД;
- JSON отдельно маркирует mock и real HTTPS результаты.

## Ограничения

- Настоящий Telegram iOS WebView и Safari на устройстве не запускались. Проверка
  safe-area — Chromium с существующим mock SDK, в том числе 375×568. Нужен ручной
  приёмочный прогон на iPhone перед отдельным решением о развёртывании.
- Флаг выключен, публичного rollout, Preview/VPS/deploy не было.
- Offline draft, который не дошёл до сервера, после полного закрытия не гарантирован.
  Intent повтора хранится только в памяти текущего запуска и текущего аккаунта.
- Текущий Backend поддерживает single_choice и один scope; несколько тестов за
  один старт и произвольный порядок вопросов не добавлялись.
- Суммарное число правильных ответов в ходе Learning не выдумывается: в текущем
  AttemptDTO его нет; показывается проверка текущего ответа и серверный итог в конце.
- Серверный повтор именно ошибочных вопросов отдельным kind пока не предусмотрен
  контрактом. Доступны защищённый разбор и повтор того же набора; legacy повтор
  ошибок сохранён при выключенном флаге.
- XP, Premium, платежи, новые зависимости и постоянное хранилище клиента не добавлены.

## Откат

Оставить/вернуть `VITE_MEDEXA_BACKEND_ENABLED=false` и пересобрать frontend в отдельно
разрешённой среде; это возвращает прежний локальный путь. PR не меняет данные и
миграции, поэтому откат этого коммита не требует обратной миграции БД.

## Изменённые файлы

- `src/backend/attempts.ts`: DTO-валидация, owner-scoped controller и immutable intents.
- `src/backend/AttemptScreen.tsx`: orchestration, timer, errors/retry и защищённый разбор.
- `src/backend/{BackendApp,client,screens}.tsx/ts`: подключение навигации, запуск и transport headers/PUT.
- `src/features/tests/{TestSession,TestResult}.tsx`: серверные представления существующих экранов; legacy функции не менялись.
- `src/pages/HomePage.tsx`: только текст о доступном resume в server-only ветви.
- `backend/app/content/api.py`: устранение устаревших capability-заглушек.
- `backend/tests/test_catalog_attempt_modes.py`, `test_content_api.py`, `test_content_cursors.py`: capability/regression checks.
- `tests/backend-attempts.test.mjs`, `attempt-fixtures.mjs`: unit/synthetic fixtures.
- `tests/backend-attempts-browser.mjs`: mobile browser scenarios.
- `tests/backend-attempts-https.mjs`, `run-attempts-https.py`: real isolated E2E.
- `tests/backend-browser.mjs`: актуализация режима запуска и временного каталога снимков.
- `.github/workflows/medexa-frontend.yml`, `.gitignore`, `package.json`: проверки и исключение сборочного каталога.
- Этот отчёт и `docs/screenshots/frontend-6b/*`.

Backend моделей/миграций, legacy движка, CSS/картинок/SDK, Preview и Production
в diff нет. Изменения нового Backend ограничены read-only каталогом и его тестами.
