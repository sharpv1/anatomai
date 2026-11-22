# ANATOMAI Telegram Core 5.0

> Историческое описание 5.0. Исправленная схема отступов и ограничения проверок описаны в [Telegram Layout 5.0.1](telegram-layout-5.0.1.md); фиксированный clearance и глобальный scrim из разделов ниже больше не используются.

Изменения ограничены платформенной интеграцией, viewport и компоновкой экрана тестирования. Вопросы, ответы, логика экзамена и дизайн карточек не изменяются. Деплой не выполняется.

## Lifecycle

Фабрика адаптера не обращается к DOM и Telegram. `init()` вызывается эффектом App, `dispose()` — его cleanup. Повторный init не добавляет подписки; после dispose допустима повторная инициализация (включая React StrictMode).

Наличие SDK в браузере не означает запуск в Telegram: проверяются initData либо известная platform. Это проверка окружения, не серверная проверка подлинности initData.

BackButton использует один стабильный bridge, вызывающий последний callback. hide/dispose снимают его через offClick. Для подписок требуются парные onEvent/offEvent. Необязательные команды проверяют доступность и версию API. requestFullscreen возвращает факт отправки запроса; подтверждение приходит через fullscreenChanged. fullscreenFailed сохраняет код в data-telegram-fullscreen-error, не объявляя запрос успешным.

## Viewport и safe-area

Адаптер публикует необработанные Telegram-метрики; CSS определяет эффективные --app-inset-* как максимум соответствующих Telegram safe/content insets и env(safe-area-inset-*). Для fullscreen сверху также учитывается clearance UI 4.5. Это сохраняет опубликованную max-модель UI 4.5, а не складывает одни и те же области на каждом уровне дерева.

Обычные экраны получают отступы через shell. В тестовом потоке shell не имеет padding и резерва навигации; фиксированный экран получает insets один раз. Header/footer не сжимаются, центральный flex-элемент имеет min-height:0 и overflow-y:auto. Выбор режима и результаты прокручиваются целиком.

Используется текущая viewportHeight для доступности footer при изменении высоты. Вне Telegram fallback — visualViewport.height / innerHeight; учитываются resize и visibilitychange. Требуется проверка поведения клавиатуры в настоящем Telegram iOS.

## Подтверждённые параметры UI 4.5

Источник: опубликованные https://preview.themedx.ru/ и /assets/index-anatomai-telegram-4-5.css, изученные 17 ноября 2026 года. Значения перенесены адресно, без цепочки патчей 4.0–4.5:

- Fullscreen clearance: max(contentSafeAreaInset.top, safeAreaInset.top, 104px); вне fullscreen дополнительный clearance равен 0.
- Отступ shell сверху: 12px + inset, при высоте до 650px — 8px + inset.
- Scrim: высота 76px + clearance, z-index 30, pointer-events:none, blur 12px; градиент rgba(245,247,251,.98/.96/.84/0) на 0/70/86/100%.
- Fullscreen navigation: 8px сверху, 12px + эффективный нижний inset снизу, z-index 31.
- Цвета, шрифты, карточки, иконки и состав навигации сохранены из исходников. Остальные визуальные правки опубликованного CSS (например, увеличение текста ответа до 15px) в этот платформенный PR не включены.

Неподтверждённое: соответствие опубликованных 104px реальной геометрии системных кнопок на всех iPhone, актуальное состояние файлов внутри VPS, pixel-perfect соответствие в нативном Telegram WebView. Дополнительные размеры для этих случаев не выдумывались.

## Проверки

```
npm ci
npm run typecheck
npm run build
npm test
npx playwright install chromium
npm run test:viewport
```

Для установленного Chromium: `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:viewport`.

Node-тесты проверяют чистую фабрику, идемпотентный lifecycle, remount, удаление подписок, единственный BackButton callback, события fullscreen и browser/старый API fallback.

Браузерный тест запускает production preview только на 127.0.0.1:4179. Он подменяет SDK, добавляет длинный DOM-контент без изменения вопросов и проверяет неподвижность header/footer, видимость footer, внутреннюю прокрутку и отсутствие document scroll. Размеры: 320×480, 375×400, 390×667, 667×375; режимы browser/Telegram/fullscreen. Всего 12 сценариев.

## Остаточные риски и ручная приёмка

- Chromium с mock SDK не заменяет Telegram на физическом iPhone. Проверить fullscreen enter/exit/failure, поворот, home indicator, клавиатуру, возврат из background, Back после нескольких ответов и повторного открытия теста.
- В наследуемом UI 4.5 scrim перекрывает часть верхнего контента. Эффект сохранён; его изменение — отдельное визуальное решение.
- CSS использует :has(), env() и dvh; требуется современный iOS/WebView. Поддержка старых клиентов отдельно не подтверждена.
- При экстремально малом viewport, где сами header/footer и системные insets выше экрана, места под вопрос не останется. Проверенный нижний landscape-размер — 667×375.
- Известные проблемы history/popstate, таймера экзамена, подсчёта пропусков и хранения прогресса остаются за пределами этого PR.
