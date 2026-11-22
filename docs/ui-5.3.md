# ANATOMAI UI 5.3 — Motion & Liquid Glass Refinement

Основа: PR #5, `fix/anatomai-ui-5.2.1`, `7a85afd`. PR #5 открыт, новая ветка `feature/anatomai-motion-5.3` создана от него. В сообщении доступен текст задания, исходные пользовательские скриншот/запись не приложены; сравнение выполнено по собственным production screenshots.

## Liquid Glass 3.0

Капсула 56px, внутренний padding 4px, иконки 20px, подписи 10px, области нажатия не менее 44×44px. Скругление, горизонтальные safe-area и bottom offset сохранены. Белая поверхность alpha .28, один слой blur(20px) saturate(160%), тонкий светлый контур, мягкий верхний блик и тень без белого ореола. Непрозрачнее fallback включается только без поддержки backdrop-filter.

Активный индикатор — один абсолютный pointer-events:none элемент под четырьмя кнопками. Его ширина вычисляется из неизменной grid-геометрии, перемещение выполняется translateX за 180ms. Кнопки не меняют ширину/позицию, active state меняет только цвет текста. Нет дополнительного фона под панелью и анимации blur.

Нижний inset применяется один раз. Старый резерв страницы сохранён, поэтому статическая главная и последние блоки не сдвигаются; резерв продолжает обеспечивать доступ к нижним элементам. Navigation routing и четыре пункта не изменены.

## Scrollbar

Реальные scroll owners: `.shell__content` (главная/каталог), `.test-session__content` (вопрос), `.test-mode-picker` и `.test-result`. Для них, а также `.subjects`, заданы scrollbar-width:none, -ms-overflow-style:none и скрытие ::-webkit-scrollbar с нулевыми размерами.

Новые правила не меняют overflow. Внешние layout-контейнеры продолжают клиповать содержимое по safe-area так же, как в 5.2.1; прокрутка остаётся у внутренних владельцев. Momentum scrolling и прежняя модель горизонтальных карточек сохранены. Полноценная горизонтальная карусель не добавлялась: `.subjects` до этой задачи уже имел overflow:hidden.

Нативный индикатор UIScrollView/WKWebView, если его показывает сам Telegram вне DOM, не контролируется этими CSS-правилами. Для его гарантированного отключения нужен доступ к нативным showsVerticalScrollIndicator/showsHorizontalScrollIndicator, которого у Mini App нет.

## Motion и состояние

- Существующие экраны главной и каталога: вход fade + translateY(6px), 180ms. Без масштабирования и анимации высоты. CSS запускается при показе страницы, а не при обычном render/scroll/input.
- Главная и каталог остаются смонтированными в скрываемых контейнерах: поиск/фильтры не теряются при смене вкладки. AppShell запоминает scrollTop по маршруту и восстанавливает его при возврате; тестовый поток сохраняет собственную прокрутку. Изменений данных/проверки/таймера/результатов нет.
- Незавершённые разделы «Конспекты» и «Профиль» не получили фиктивных экранов; сохранено прежнее поведение. Индикатор перемещается на все четыре вкладки.
- Карточки: 160ms для поверхности/границы и мягкого pressed shadow без scale.
- Кнопки: 160ms для opacity/поверхности при нажатии, без изменения размеров.
- Прогресс: плавное изменение ширины существующих небольших bars, 180ms; существующие состояния ответа сохранены.
- Результат теста: лёгкий вход 180ms; раскрытие разбора не перезапускает анимацию всего результата.
- Reduced-motion отключает новые animations/transitions, включая индикатор. Тяжёлых зависимостей, blur-анимаций и постоянных will-change слоёв нет.

## Главная до/после

DailyFocusCard, HomePage, dailyFocus data, AppHeader, StatisticsSection, SubjectsSection, app.css, брендовые цвета, тексты и композиция не менялись. Разрешённые общие pressed/enter эффекты влияют только на момент взаимодействия.

Сравнены production build `7a85afd` и 5.3 в Chromium с mock SDK и reduced-motion, на 375/390/430px, сверху и в конце прокрутки. Scroll geometry совпадает. Во всех шести PNG-сравнениях — **0 изменённых пикселей вне области навигации и её тени**. Блок вопроса также имеет прежнюю высоту: 381,4 / 383,6 / 389,5px. Для снимков с motion нужно дождаться окончания перехода; статический дизайн не изменяется.

Повторение:

```
# BEFORE_URL должен обслуживать dist из 7a85afd; AFTER_URL — текущий production build.
BEFORE_URL=http://127.0.0.1:4182 AFTER_URL=http://127.0.0.1:4173 CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/ui-motion-comparison.mjs
COMPARISON_DIR=/workspace/work/ui53-comparison python tests/compare-home-images.py
```

Python-сравнение требует Pillow; исходные PNG и geometry.json сохраняются в COMPARISON_DIR. JPEG previews остаются промежуточными файлами сравнения.

## Проверки

- `npm run typecheck` — успешно.
- `npm test` — 15 unit-тестов Core/insets/BackButton/zoom lock/карточек/серии проходят.
- `npm run build` — успешно.
- `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:viewport` — 21 геометрический сценарий browser/expanded/fullscreen на ширинах 375/390/430px, коротких экранах и landscape; плюс полные обучения/экзамена и отдельный motion-сценарий с reduced-motion выключенным.
- Motion-сценарий подтверждает промежуточную transform-позицию работающего индикатора, постоянные bounds кнопок >=44×44, отсутствие scrollbar при рабочем scrollTop, сохранение query и позиции главной, отсутствие повторного входа при scroll/input, полное отключение нового motion при reduced-motion.
- Прежние UI-проверки проходят с reduced-motion для стабильного измерения геометрии, а реальное движение проверяется отдельно. Long questions/answers, footer, BackButton, keyboard-resize, native/browser fallback и zoom lock сохранены.
- `git diff --check` и сверка неизменности запрещённых файлов — успешно.

## Ограничения

Настоящие iPhone, Telegram iOS WebView и Safari не запускались. WebKit в окружении недоступен из-за системных библиотек. Проверки Chromium и mock SDK не доказывают отсутствие нативного индикатора WKWebView, реальную плавность на iPhone или работу физической клавиатуры/жестов. На устройстве проверить native scrollbar, glass/contrast, пропуски кадров, fullscreen/expanded, keyboard, BackButton и zoom lock.

Backend, API, авторизация, тестовые данные, алгоритмы режимов и MEDEXA не изменены. Merge и deploy не выполнялись.
