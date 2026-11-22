# ANATOMAI — серверные попытки и восстановление истории

База: `feature/anatomai-user-app-final`, `25b5797efe707144333e3f44ab9aade21388edc1`.
Исправление: `fix/anatomai-server-attempt-history`.

## Подтверждённая первопричина

В исходном `src/main.tsx` выбор `BackendApp` зависел только от build-time флага
`VITE_MEDEXA_BACKEND_ENABLED === 'true'`. При отсутствии opt-in запускался `App`,
включая открытие из Telegram. В `.env.example` остаётся `false`.

Legacy `App.startTopic` монтировал локальный `TestSession/useTestSession`, а
`App.finishTest` добавлял результат в React `entries`. Этот путь **не вызывает**
`POST /api/v1/attempts` и не пишет в PostgreSQL. После перезагрузки `entries=[]`.
Отображение Telegram-имени через SDK в этой ветви не означает подтверждённую Identity.
Поэтому внешне пройденный тест мог не оставить ни одной серверной попытки.

Серверные компоненты и транзакции уже присутствовали в базе 6b и работали при opt-in.
Создавать второй движок, отдельную историю или переносить локальные результаты
в Backend не требовалось. Исправлен путь, который фактически выбирает приложение.

Установленную на VPS сборку и её переменные не исследовали: к VPS/Preview/Production
не подключались. Причина воспроизводится и проверяется на default production build
указанной ветки, без изменения production-конфигурации.

## Изменения

1. `Application` выбирает существующий `BackendApp`, если включён browser opt-in,
   присутствуют Telegram `initData` / launch-параметры или ранее в этой вкладке уже
   выбран серверный контур. Launch data определяют **маршрут**, а не полномочия:
   HMAC, auth_date, cookie, ownership и CSRF проверяются прежним Identity API.
2. Серверный путь не заменяется локальным при 401/409/412/503, offline или исчезновении
   SDK. Ошибка отображается через существующий UI; мутации повторяются прежним
   контроллером с исходными Idempotency-Key/If-Match.
3. На start **и finish** локального демотеста повторно проверяется позднее появление
   Telegram launch. Это закрывает промежуток до очередного polling tick.
4. В sessionStorage сохраняется только `anatomai:server-mode=1`. Здесь нет user ID,
   initData, cookie, ответа, результата или истории. Marker не даёт прав и не смешивает
   владельцев. При блокировке storage текущая страница всё равно работает через Backend;
   при новом открытии Telegram серверный путь определяется launch data.
5. API base валидируется и при Telegram-запуске без build-time opt-in. Не допускаются
   внешние origin/опасный путь или молчаливая подстановка другого Backend.
6. Обычный браузер без Telegram launch, marker и opt-in сохраняет отдельную локальную
   демоверсию. Она не объявляется источником серверной истории. Это намеренное отличие
   от старого правила «flag=false отключает Backend даже внутри Telegram».

Значения `.env.example` не изменены; обновлён только комментарий о семантике.
CSS, палитра, карточки, шапка, навигация, Telegram adapter, движок и миграции Backend
не изменены. Ничего не удаляется из существующих БД.

## Реальная проверка сохранения

Использован отдельный PostgreSQL **16.16**, свежая схема `0010_progress_statistics`,
синтетический published банк из двух вопросов и настоящие FastAPI/HTTPS/cookie/CSRF.
Подменяется только Telegram host SDK, HMAC проверяется сервером. Ни API, ни БД в E2E
не заменяются mock. Frontend — обычный `dist`, собранный без включения opt-in.

Прямые SQL assertions в изолированной БД:

| Момент | Проверено |
| --- | --- |
| Старт Learning из интерфейса | `attempts=1`, одна in_progress |
| Learning завершён | одна completed, `attempt_responses=2` |
| Перезагрузка и открытие «Моя статистика» | одна запись истории, серверный результат 50% |
| Возобновление Learning после перезагрузки | checked ответ сохранён, новый start не отправляется |
| Возобновление Exam | сохранённый изменённый выбор восстановлен |
| Learning + Exam + timeout после закрытия страницы | **3 completed attempts, 6 attempt_responses**, сводка completed_tests=3 |

До повторного HTTP-запроса после закрытия страницы SQL подтверждает timeout,
выполненный DB-backed finalizer. Отдельно проверяется потеря ответа после commit:
повтор отправляет прежние key/If-Match и не создаёт второй результат.

Артефакты: [скриншоты и JSON](screenshots/server-attempt-history/).
Все файлы БД/ключей и контейнер теста создаются отдельно и удаляются после проверки;
существующие базы не используются.

## Автоматические регрессии

- Unit: маршрутизация по initData/launch URL, отсутствие авторизации по одному лишь
  объекту SDK; обязательная валидация API base независимо от browser opt-in.
- Browser: поздний SDK непосредственно перед start/finish, недостоверный proof,
  потеря SDK и reload, offline/retry — локальный тест/результат не открываются.
- Browser: start API отвечает 503 — видимая ошибка без локального fallback;
  явный повтор использует исходный ключ.
- Learning/Exam: 375/390/430 px, короткий экран, resume, idempotency, 401/409, смена
  аккаунта, BackButton и отсутствие активных Exam-ключей.
- Legacy regression ограничена **браузером без Telegram launch**. Старый сценарий
  локального тестирования внутри Telegram намеренно больше не является допустимым.
- Сравнение Главной выполняется production-vs-production, одинаковыми mock-данными
  и без Telegram launch для демоверсии; CSS не менялся. Это исключает различия
  различия dev/prod CSS. Content hash production CSS должен совпасть; допускаются
  лишь GPU rasterization-округления до 2/255 на <0,1% пикселей, без изменений геометрии.
- GitHub Actions запускает default-off entry regression, обе сборки и E2E на `dist`.

## Результаты

| Проверка | Результат |
| --- | --- |
| TypeScript | PASS |
| Frontend unit | **65 passed** |
| Default production build | PASS |
| Browser opt-in production build | PASS |
| Default-off entry / late SDK start+finish / reload / offline | PASS, без локального fallback |
| Server Learning/Exam, 375/390/430 px | PASS, включая короткий экран, start 503 и повтор исходного запроса |
| Browser-only demo regression | PASS, 375/390/430 и 375×400 |
| Home / Profile / Statistics / каталог / конспекты, 6a regression | PASS |
| Production Home visual regression | PASS: CSS content hash совпал, rasterization в установленном допуске |
| Настоящий HTTPS E2E + PostgreSQL 16 | PASS: 3 completed attempts / 6 responses, история после повторного открытия |
| Ruff тестового Python runner | PASS |

E2E ожидает только начальный 401 `/auth/session` до входа. Неожиданных API-ошибок
после успешной авторизации не зафиксировано. Mock UI и настоящий E2E маркируются
отдельными JSON-отчётами; запросы к Production отсутствуют.

Команды:

```sh
npm run typecheck
npm test
npm run build
# Только изолированная проверка прежнего browser opt-in, не production-настройка:
VITE_MEDEXA_BACKEND_ENABLED=true npm run build -- --outDir dist-backend
npm run test:server-entry
MEDEXA_UI_URL=http://127.0.0.1:5180 npm run test:attempts:ui
npm run test:backend:local
backend/.venv/bin/python tests/run-attempts-https.py
```

Для HTTPS E2E нужен Docker с postgres:16-alpine и установленный тестовый Python 3.12
(`cd backend && uv sync --locked`). Клиент доверяет лишь в тестовом контексте временной
самоподписанной loopback-сертификации; приложение не отключает серверную HTTPS-проверку.

## Ограничения и приёмка

- Настоящий Telegram iOS WebView не запускался. Его cookie/safe-area/BackButton нужно
  подтвердить на устройстве после отдельного разрешения на установку исправления.
- Требуется доступный same-origin HTTPS Backend с Identity и опубликованным банком.
  При его недоступности приложение показывает ошибку, а не несохраняемый локальный тест.
- Неотправленные offline-ответы не объявляются сохранёнными; после закрытия доступны
  только действительно зафиксированные сервером данные.
- Старые локальные результаты не импортируются и не маскируются под PostgreSQL-историю.
- Это исправление исходников и PR. Работающая установленная версия не менялась,
  деплой и переключение production-конфигурации не выполнялись.

## Изменённые файлы

- `src/Application.tsx`, `src/main.tsx`: выбор и фиксация серверного контура.
- `src/App.tsx`: запрет позднего локального start/finish при Telegram launch.
- `src/backend/config.ts`: launch hint и API-base validation.
- `.env.example`: только документационный комментарий; значения прежние.
- `tests/backend-api.test.mjs`, `server-entry-browser.mjs`: регрессии входа.
- `tests/backend-attempts-browser.mjs`: default-off server mode / start 503.
- `tests/backend-attempts-https.mjs`, `run-attempts-https.py`: default build,
  SQL-проверка attempts/responses, история после reload и нового открытия.
- `tests/backend-browser.mjs`, `backend-local-regression.mjs`: корректная граница demo.
- `.github/workflows/medexa-frontend.yml`, `package.json`: выполнение проверок.
- Этот отчёт и `docs/screenshots/server-attempt-history/*`.
