# ANATOMAI UI 6.1.2 — Telegram Back Navigation Fix

Основа: `fix/anatomai-ui-6.1.1-telegram-ios-hotfix`, коммит `31466a8566ef59e6baa2cbf05859534b25c5d8ed`.
Новая ветка: `fix/anatomai-ui-6.1.2-native-back`. Merge и deploy не выполнялись.

## Аудит и исправление

В 6.1.1 внутренняя квадратная стрелка скрывалась по snapshot программного BackButton: наличие владельца, зарегистрированного callback и `isVisible === true`. Кнопка панели Telegram, работу которой на iPhone подтвердил пользователь, может не отражаться в этом флаге. Поэтому эта проверка оставляла дублирующую стрелку.

Определение host-контекста отделено от доступности/видимости программной кнопки. Для UI-распознавания требуются WebApp lifecycle-методы ready/expand и непустая initData либо известная platform (ios, android, android_x, tdesktop, macos, weba, webk, unigram). Одного объекта window.Telegram недостаточно. SDK с пустой initData и unknown/неизвестной platform сохраняет внутреннюю навигацию. Это эвристика интерфейса, а не серверная проверка подлинности данных Telegram.

Adapter публикует отдельный реактивный snapshot контекста через существующую подписку. Он обновляется при init, позднем SDK, смене/исчезновении SDK и dispose. Hook использует его для отображения стрелки. В подтверждённом контексте Telegram стрелка скрывается независимо от isVisible. В браузере или при неопределённом контексте остаётся доступной.

BackButton binding, один bridge, владение экраном, защита от повторного события в одном цикле, подтверждение потери прогресса, popstate и cleanup сохранены. TestResult уже использует тот же hook: его разметка, статистика и действия не изменены. Native callback вопроса ведёт в каталог через onExit, результата — через onBack; приложение не вызывает close(). При недоступном программном API продолжает слушаться popstate. Если клиентская кнопка не посылает ни BackButton callback, ни событие истории, перехватить её поведение из JavaScript невозможно.

Существующий класс `test-session--native-back` включает двухколоночную сетку без колонки стрелки. Название дисциплины, номер вопроса и прогресс начинаются у левого края; дополнительный CSS не потребовался. Карточки ответов, объяснения, нижние действия, экран результата и остальные страницы не изменены.

## Проверки

- `npm run typecheck`: успешно.
- `npm test`: 23 теста, успешно. Новые проверки отделяют контекст от видимости, проверяют поздний/исчезающий SDK, неопределённый контекст, lifecycle и очистку.
- `npm run build`: успешно.
- `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/viewport.mjs`: адаптивная матрица 54 сценария (320/375/390/430 px, browser/expanded/fullscreen и разные высоты), полный проход обучения/экзамена и motion-проверка — успешно. Проверяются прокрутка, цвета ответов, нижние действия, повторный вход, отсутствие горизонтального переполнения.
- `AFTER_URL=... CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/telegram-ios-hotfix.mjs`: 14 lifecycle-сценариев (семь вариантов SDK × expanded/fullscreen) и четыре результата 0/20/80/100% — успешно. Включены SDK в браузере с unknown platform, отсутствие SDK, поздний SDK/API, неизвестная видимость, ошибка show, отмена/подтверждение выхода, один переход, повторный вход и cleanup на результате. При ошибке show отдельно проверен возврат через popstate.
- `BEFORE_URL=... AFTER_URL=... CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/native-back-comparison.mjs`: восемь PNG главной (верх/низ × 320/375/390/430 px) побайтово идентичны сборке 31466a8. При неизвестном isVisible после исправления стрелка отсутствует, meta и progress совпадают с левой границей header. Исходные CSS не изменены.
- `git diff --check`: успешно.

Все UI-проверки выполнены в Chromium с mock Telegram SDK. Реальный Telegram iOS и Safari в этом окружении не запускались. Сообщение пользователя подтверждает работу верхней кнопки на его устройстве; самостоятельно подтвердить нативное закрытие/сохранение состояния в iOS здесь нельзя. На устройстве остаётся проверить выход с вопроса с подтверждением, с результата, повторный вход и поведение клиентской панели в обоих режимах Telegram.

## Изменённые файлы

- `src/platform/telegram/TelegramPlatformAdapter.ts`
- `src/platform/telegram/useTelegramBackButton.ts`
- `src/features/tests/TestSession.tsx`
- `tests/telegram-platform.test.mjs`
- `tests/telegram-ios-hotfix.mjs`
- `tests/native-back-comparison.mjs`
- `docs/ui-6.1.2.md`

Главная, XP/streak, каталог, профиль, конспекты, Liquid Glass, TestResult, данные, движок, zoom lock, backend и MEDEXA не изменялись.
