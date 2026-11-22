# MEDEXA / ANATOMAI — Frontend integration 6a

Основа: `ac1d822063505ce52d115d0200dbc62decd93ef3`.
Ветка: `feature/medexa-frontend-integration-6a`.
База Draft PR: `feature/medexa-progress-statistics`.

## Граница этапа

Это опциональный **read-only режим нового Backend**, а не замена тестового движка.
Флаг выключен по умолчанию. Legacy App, его Learning/Exam, локальный банк вопросов,
обработчики результатов и текущая навигация остаются прежними при выключенном флаге.
Новые UUID каталога не сопоставляются с legacy ID по названию или положению.
Локальные результаты не отправляются на сервер, не импортируются как достоверные и
не объединяются с серверной историей. Backend, миграции и рабочие окружения не менялись.

При включённом флаге доступны авторизация, опубликованный каталог, темы/тесты,
справочный разбор, текстовые конспекты, Home/Profile/Statistics и история аккаунта.
Запуск/возобновление **серверных** Learning/Exam — этап 6b. Кнопки режимов сохраняют
классы/размеры/оформление, но явно aria-disabled и сопровождаются сообщением
недоступности. Сохранённая серверная попытка отображается как информация, не запускается
локально. Ни `/attempts` mutations, ни XP, ни платежи, ни reset API не вызываются.

## Конфигурация и безопасное включение

В `.env.example`:

```dotenv
VITE_MEDEXA_BACKEND_ENABLED=false
VITE_MEDEXA_API_BASE=/api/v1
```

Включение — только точное `VITE_MEDEXA_BACKEND_ENABLED=true`. Vite подставляет флаг
при dev/build; после изменения нужен restart dev server либо новый build.
`VITE_*` публичны: **не помещать туда bot token, cookie, CSRF key или DB credentials**.

API base разрешает только same-origin path, например `/api/v1`. Абсолютные URL,
protocol-relative URL, dot segments, fragments и перенаправления отклоняются.
Неверная opt-in конфигурация показывает ошибку без сетевого fallback.
Флаг не является механизмом авторизации — права всегда проверяет Backend.

Для настоящего dev/test соединения требуется выделенный **HTTPS same-origin**
frontend и reverse proxy `/api/v1` к новому изолированному Backend. Указать Backend
`MEDEXA_APP_ORIGIN`, точно совпадающий с origin Frontend, сохранить HTTPS и
`__Host-medexa_session; Secure; HttpOnly; SameSite=Lax`. Не отключать HTTPS/CSRF и
не менять SameSite ради localhost. В этот PR proxy/Production/Nginx-конфигурация
не включены. `vite.config.ts` не перенаправляет запросы на какой-либо сервер.
При отсутствии proxy opt-in режим показывает ошибку, а не подставляет legacy data.
Не направлять локальные проверки на Production API.

## Клиент и Identity

`src/backend/client.ts`:

- cookie requests с credentials=include, cache=no-store, redirect=error;
- JSON envelope, request_id и типизированные DTO с runtime-проверкой;
- X-CSRF-Token для авторизованных POST/PATCH/DELETE, из подтверждённого SessionView;
- auth exchange — существующий CSRF-exempt `POST /auth/telegram` с initData;
- timeout 10 секунд, AbortController, различение network/timeout/cancel/HTTP/protocol;
- отмена персональных запросов и запрет публикации устаревших ответов при смене scope;
- никаких Authorization bearer, cookie чтения из JS, persistent cache или автоматических
  повторов мутаций. initData/CSRF/ответы не записываются в console или storage.

`src/backend/auth.ts` использует только фактический Identity API:

1. GET `/auth/session` — восстановление серверной сессии.
2. Launch user ID — лишь сигнал смены аккаунта, **не авторизация**. При совпадении
   с уже подтверждённой сессией повторный вход/старое initData не отправляется заново.
3. При отсутствии сессии/смене пользователя — POST `/auth/telegram` с исходным initData
   и действительной IANA-зоной устройства для нового пользователя. Подпись, auth_date,
   replay и создание cookie проверяет только существующий Backend.
4. После exchange — повторный GET `/auth/session`, подтверждающий принятую cookie и
   того же server user.id. Если cookie блокируется браузером, ready не публикуется.
5. Противоречие initData user и initDataUnsafe user блокирует вход до свежего согласованного
   контекста. Непарсируемые launch user данные не разрешают восстановление по unsafe hint.
6. Подтверждённый SessionView.user — источник имени/фото. initDataUnsafe не создаёт
   пользователя, сессию, роль или статистику. При auth loading/error шапка нейтральная.

Auth exchange сериализован: устаревший Set-Cookie не гоняется с новым логином в том же
контроллере. GET/POST Identity ограничены timeout, устаревший результат не публикуется.
На личный HTTP 401 скоуп очищается и запускается Identity bootstrap; исходная операция
автоматически не повторяется. Просроченный/повторно использованный initData не превращается
в «демо-вход»: нужна свежая Mini App launch data из Telegram.

В обычном браузере существующая валидная cookie может восстановить свой аккаунт без
initData; первый вход без cookie/initData показывает предложение открыть Mini App из
Telegram. Ошибки сети допускают явный retry. При pageshow/focus/возврате видимости
сессия перепроверяется. Изменение launch data/SDK отслеживается без сетевого polling;
при позднем/заменённом SDK используется lifecycle существующего platform adapter.

## Скоуп данных и навигация

`src/backend/react.tsx` — небольшие локальные resource hooks, без новой query library.
Ресурсы/страницы живут внутри подтверждённого аккаунта, ключи запроса включают параметры;
при смене ключа старый результат сразу скрывается. Abort и generation guards отменяют
публикацию старого ответа даже при задержанном транспорте. Пагинация использует только
next_cursor сервера; load-more сериализован и берёт актуальный cursor из ref.
Нет кеша, общего для разных пользователей, localStorage/IndexedDB, токенов в URL или
глобальной коллекции результатов.

Четыре вкладки и AppShell/BottomNavigation переиспользуются. Opt-in переходы хранят
только навигационные ID в отдельном `history.state.medexa6a`, с проверкой owner. Legacy
history.state не интерпретируется как серверные данные. Telegram BackButton остаётся
в существующем adapter/hook: один владелец на видимый экран; browser popstate обрабатывает
контейнер, без двойного перехода. Server callbacks не встраиваются в local test engine.

При перепроверке сессии личное содержимое скрывается и перечитывается; вкладка/навигация
того же аккаунта сохраняются, временные диалоги/поиск/scroll могут сбрасываться. При смене
аккаунта выбирается нейтральная Главная. Это безопасная граница read-only этапа;
будущий attempt UI должен восстанавливаться из Backend, а не из клиентского score.

## Фактические маршруты и представления

DTO сверены с `backend/app/identity/{api,schemas}.py`, `content/{api,schemas}.py`,
`progress/{api,schemas}.py`, а также LEARNING.md / EXAM.md / PROGRESS.md.

| Представление | API и смысл |
|---|---|
| Авторизация | GET `/auth/session`, POST `/auth/telegram`; SessionView.user и csrf_token |
| Home | `/me/home`, `/me/recommendations`, `/me/daily-topic`, `/disciplines`; headline, реальная сводка и предметы |
| Предмет → Конспекты | UUID дисциплины из каталога передаётся напрямую, без legacy mapping |
| Вопросы дня | Daily-topic availability и точный topic UUID → reference-questions; empty/withdrawn честные |
| Каталог | `/disciplines`, `/topics?discipline_id=...`, `/test-definitions?topic_id=...`; counts и available_modes из DTO |
| Тема | `/topics/{id}`, `/disciplines/{id}`, `/me/topics/{id}/summary`; null best/errors остаются «—» |
| Ответы и разбор | `/topics/{id}/reference-questions?query&cursor&limit`; server number, options, correct_option_ids; не экзамен |
| Конспекты | `/notes?discipline_id&query&cursor`, `/notes/{id}`; plain_text экранируется React, нет вымышленных материалов |
| Profile | `/me/statistics`, `/me/progress`, `/me/achievements`; подтверждённое имя/фото, реальная серия и информация в существующем Settings dialog |
| Statistics | `/me/statistics`, `/me/activity`, `/me/attempts?cursor`, `/me/achievements`; существующие сводка/неделя/история/achievement disclosure |

Все пользовательские значения берутся из фактических полей. Не создаётся фиктивный
TestDefinition с UUID сервера ради загрузки локальных вопросов. В серверный справочник
переходит только отдельная read-only projection в уже существующий QuestionReviewPage.
Backend EXAM_REFERENCE_LOCKED показывает ошибку и не раскрывает ответы.

Счётчики при пустой истории — достоверные серверные 0; nullable среднее/время — «—».
XP и уровни остаются недоступными. Состояния достижений только из API; прежний registry
переиспользуется для иконок, не для расчёта server unlock. granted_at=null не выдаётся
за реальное награждение. Никакие новые серверные события/награды не создаются.

Каталог, темы, тесты, notes/reference и история поддерживают серверную пагинацию.
На Home предметов до четырёх по прежнему размеру блока. Быстрая практика выбирает
первый непустой опубликованный test из первой страницы (до 30), открывает тему, не
запускает серверный движок. Если такого кандидата нет, карточка не выдумывается.
Assets конспектов/скачивание файлов и детальный result-review истории не добавляются
как новые интерфейсы: для них нет готового UI в текущем scope. Plain text конспекта
доступен, файл без текста имеет честный статус недоступности в этом интерфейсе.

## Дизайн и scope

Переиспользованы HomePage, ProfilePage, StatisticsPage, QuestionReviewPage, DailyFocusCard,
StatisticsSection, SubjectsSection, AppHeader, AchievementGrid и их прежние CSS-классы.
Не менялись глобальные CSS, палитра, safe-area, zoom lock, platform adapter, навигация
из четырёх вкладок, исходные WebP и логика Learning/Exam. Новые серверные контейнеры
используют те же карточки/заголовки; состояние загрузки/ошибки — существующий library-empty.
Реальные строки/количество карточек могут менять высоту контента естественным образом.

## Проверки

- TypeScript: успешно.
- `npm test`: **53 passed** — все 39 прежних и 14 новых client/auth/config/DTO тестов.
- Production build: успешно с выключенным флагом и с opt-in флагом; CSS одинаковый.
- Chromium на 375/390/430: bootstrap/reopen, смена пользователя, Home/Statistics/Profile,
  каталог/тема, ответы/поиск/возврат, notes, пустые данные, offline/retry, session expiry,
  отсутствие horizontal overflow и один Telegram BackButton callback.
- Дополнительно: 375×568, mock expanded/fullscreen safe-area, длинные медицинские
  формулировки/имена, история следующей страницы, plain text note и browser Back,
  reference lock/retry. Ни одного запроса к Production API.
- Прежний `tests/ui83.mjs` через изолированный wrapper: **9 сочетаний** ширины
  375/390/430 × browser/expanded/fullscreen, плюс 375×400 и длинная тема. Learning feedback,
  подсчёт, пропуск, повтор ошибок/retake, Exam secrecy, разбор и safe-area — успешно.
- Default-off Home сравнена с точным базовым коммитом на одном Chromium/fixed time:
  **побайтно одинаковые PNG на 375/390/430**. API-запросов в выключенном режиме нет.
- Новый CI: typecheck, unit, оба build, mock browser tests, exact baseline comparison,
  прежняя UI-регрессия. Итоговый статус — checks Draft PR.

UI-проверки используют **изолированные loopback Vite servers и mock API/SDK**. Скриншоты
с пометкой server показывают синтетические тестовые данные, не реальные показатели
аккаунта и не Production. Backend-код не менялся и повторно его полный Pytest здесь
не запускался; фактические DTO/маршруты прочитаны из источников. Живой end-to-end
Frontend↔FastAPI↔PostgreSQL с реальными cookies и настоящий Telegram iOS/WebKit в этом
окружении не проверялись. Перед включением флага в рабочем окружении нужен отдельный
HTTPS same-origin/iOS gate (cookie persistence, fresh initData, reopen, keyboard/safe-area).

## Скриншоты

Все изображения — тестовое окружение Chromium, mock Telegram fullscreen/expanded.

- [Home: серверный режим, 390](screenshots/frontend-6a/home-server-390.png)
- [Profile: серверный режим](screenshots/frontend-6a/profile-server-390.png)
- [Statistics и история](screenshots/frontend-6a/statistics-server-390.png)
- [Тема и опубликованные тесты](screenshots/frontend-6a/topic-server-390.png)
- [Ответы и разбор](screenshots/frontend-6a/review-server-390.png)
- [Пустая история](screenshots/frontend-6a/empty-server-390.png)
- [Короткий экран](screenshots/frontend-6a/short-server-375.png)
- [Default-off Home 375](screenshots/frontend-6a/home-local-375.png),
  [390](screenshots/frontend-6a/home-local-390.png), [430](screenshots/frontend-6a/home-local-430.png)

## Изменённые файлы

- `src/backend/{contracts,client,auth,config,presentation}.ts`, `react.tsx`, `screens.tsx`,
  `BackendApp.tsx` — frontend integration, не новый серверный Backend.
- `src/main.tsx` — opt-in выбор источника; `src/App.tsx` и test engine не менялись.
- `src/components/{AppHeader,DailyFocusCard,DailyQuestions,StatisticsSection,SubjectsSection}.tsx`.
- `src/pages/{HomePage,ProfilePage,StatisticsPage,QuestionReviewPage}.tsx`.
- `src/features/library/AchievementGrid.tsx` — опциональные server props, legacy по умолчанию.
- `.env.example`, `package.json` (только scripts), `.github/workflows/medexa-frontend.yml`.
- `tests/backend-api.test.mjs`, `backend-browser.mjs`, `backend-local-regression.mjs`.
- Этот отчёт и новые снимки в `docs/screenshots/frontend-6a/`.

## Откат

Оставить/вернуть `VITE_MEDEXA_BACKEND_ENABLED=false` и пересобрать Frontend в отдельно
согласованном окружении; клиент полностью вернётся к прежней local App. Серверные
данные не удаляются, не преобразуются в local entries и не зависят от флага. Откат
коммита не требует миграции БД. Не откатывать Backend/schema вслед за UI-флагом.

Main, Preview, Production, действующие базы и старый Backend не менялись.
Merge и deploy не выполнялись. Локальные тестовые серверы не являются развёртыванием.
