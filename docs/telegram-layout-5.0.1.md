# ANATOMAI Telegram Fullscreen & Safe Area Fix 5.0.1

Основа: PR #1, `feature/anatomai-telegram-core-5`, коммит `75b6a334d30a4957133a15302ca6fa30ed4dabd0`. На момент начала работы PR открыт и не объединён. Исправления находятся в отдельной ветке `fix/anatomai-telegram-layout-5.0.1`; PR направлен в ветку Core 5.0, чтобы показать только исправления адаптации.

## Установленные причины

1. **Верхняя пустая область.** Core 5.0 принудительно сохранял минимум 104px даже при меньших актуальных insets. Глобальный `body::before` высотой `76px + clearance` визуально маскировал первые 180px экрана. Это сочетание отступа и перекрывающего слоя, а не доказанное суммирование всех 150–200px в padding. `viewportStableHeight` также задавал min-height shell и не подходил для меняющейся видимой области. Данных с конкретного iPhone нет: точное разложение его 150–200px не измерено.
2. **Карточки под Telegram-кнопками при прокрутке.** Главная и каталог прокручивались через document. Их начальный padding уходил вверх вместе с контентом; защитный overlay маскировал контент вместо ограничения области прокрутки.
3. **Высокая навигация.** Использовались `12/18px + safe-bottom`, а shell отдельно резервировал `108px + safe-bottom`. Кроме того, max(SDK, CSS env) мог повторно вводить браузерный inset, когда SDK явно сообщал ноль для уже исключённой host-области.
4. **Прямоугольники внутри цветных ответов.** `.test-choice.correct span`, `.wrong span`, `.selected span` окрашивали одновременно букву, radio и текст. По специфичности они перекрывали прозрачный фон текста. Селекторы ограничены `.test-choice__letter`; зелёный/красный фон всей карточки и палитра сохранены.

## Новая схема

Официальные определения: https://core.telegram.org/bots/webapps#safeareainset и https://core.telegram.org/bots/webapps#contentsafeareainset. System safe-area описывает вырезы/системную навигацию, content safe-area — дополнительную область Telegram UI внутри системной безопасной области.

Для каждого края:

```
system = конечное неотрицательное SDK safeAreaInset[edge], если доступно;
         иначе env(safe-area-inset-edge, 0px)
content = конечное неотрицательное contentSafeAreaInset[edge], иначе 0
inset = system + content
```

Это две разные последовательные области; CSS env не прибавляется к SDK system inset. Явный SDK 0 сохраняется. В fullscreen нет фиксированного минимума 104px. Например, 59px system + 45px Telegram действительно дают 104px; 20 + 32 дают 52px; expanded с 0 + 0 даёт 0px.

- Shell применяет верхнюю защиту один раз и имеет текущую видимую высоту. Его внутренний scrollport начинается ниже Telegram/system UI и клипует прокрутку на этой границе.
- Декоративное матовое покрытие ограничено защищённой полосой, больше не заходит на читаемый контент. Удалён глобальный body-overlay.
- Навигация — несжимаемый элемент flex-компоновки с теми же четырьмя пунктами. Bottom padding = max(8px, inset-bottom), не `8px + inset`. Резерва 108px больше нет: высота панели учитывается раскладкой.
- В тестовом потоке shell учитывает bottom inset один раз. Header/footer не сжимаются, центральная область имеет min-height:0 и overflow-y:auto. Выбор режима и результаты прокручиваются в доступной области целиком.
- Шрифты, цвета, SVG, текст, структура карточек и навигационные пункты не менялись. Корректируется геометрия и область применения существующих цветов ответов.
- Текущая высота = минимум положительных Telegram viewportHeight, visualViewport.height и innerHeight. Stable height остаётся диагностической метрикой и не управляет геометрией. Visual viewport offsetTop учитывается при панорамировании, resize/scroll и visibilitychange очищаются в dispose.
- viewportChanged подписывается всегда при доступном event API; safe-area/fullscreen события и поля — начиная с SDK 8.0. Снимаются только фактически зарегистрированные подписки. Lifecycle и стабильный BackButton bridge Core 5.0 сохранены.
- Вне Telegram SDK может отсутствовать: используются visualViewport/innerHeight и CSS env. Новых глобальных layout-правил для html/body не добавлено; изменения ограничены shell и тестовым экраном.

## Автоматические проверки

```
npm run typecheck
npm test
npm run build
CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:viewport
```

7 unit-тестов: lifecycle/remount/dispose, единственный актуальный BackButton callback, fullscreen success/failure, отсутствие SDK, старые версии API, явный ноль/fallback insets, нестабильная высота/offsetTop, очистка resize/scroll/visibility listeners.

21 UI-сценарий в Chromium с mock SDK: 375×812, 390×844, 430×932; 375×400, 390×480, 430×400 и landscape 667×375. Для каждого — browser, Telegram expanded и fullscreen. Проверяются:

- Начальная позиция header относительно метрик, отсутствие искусственного clearance и маскирующего слоя.
- Компактная панель и отсутствие перекрытия контента.
- Прокрутка главной до нижних блоков и длинного каталога.
- Главная → Тесты → выбор режима → Вопрос → Назад → Главная.
- Поиск и уменьшение viewport при фокусе; stale SDK stable height не раздувает shell.
- Длинный вопрос и длинные варианты (только DOM-fixtures тестового окружения).
- Зелёная/красная карточки и прозрачный фон текста/radio.
- Неподвижные header/footer, доступная кнопка Далее, внутренний scroll без document scroll.
- Переход fullscreen → expanded, обновление всех inset-событий и явный bottom=0.
- Повторное открытие через reload, единственные SDK listeners; скрытие fullscreen-кнопки в browser/fullscreen/тесте.

## Ограничения и ручная проверка

Настоящий iPhone и Telegram iOS WebView не запускались. Обычный Safari также не проверен непосредственно. Playwright WebKit скачан, но окружению не хватает системных библиотек (GTK4, Graphene, HarfBuzz ICU, Manette, Hyphen, GLES); UI-проверки выполнены только в Chromium. Resize после focus моделирует клавиатуру, но не является реальным открытием iOS keyboard. Reload моделирует повторное открытие, но не процесс восстановления WebView Telegram.

На устройстве проверить стартовые/асинхронные insets, iframe/WebView resize, смену orientation, fullscreen enter/exit/failure, клавиатуру с панорамированием visualViewport и возвращение из background. Если клиент 8.0 временно сообщает нулевые insets, защита обновится при SDK-событии; неподтверждённый фиксированный fallback намеренно не вводится. Физическую геометрию Telegram-кнопок по браузерному mock подтвердить нельзя.

Backend, авторизация, тестовые данные и логика ответов/таймера не изменены. MEDEXA не затрагивался. Merge и deploy не выполнялись.
