# MEDEXA Backend 2.0 — 3b.1: MFA и медицинские черновики

Это **первая из трёх частей этапа 3b**, а не готовый импортёр.
Основа — Content commit `62eb0e4cd95106080d8fb572eed27ae923307938`;
Draft PR направлен в `feature/medexa-backend-content`.
Требования: [архитектура, §5/6/9/11–14](../docs/MEDEXA_BACKEND_ARCHITECTURE.md).

В этом PR реализованы TOTP step-up, операторское enrollment/recovery, роли и
MFA-gated API для черновиков каталога, источников и вопросов. **Upload, XLSX/DOCX,
quarantine/staging, worker, review/publish/withdraw, отчёты и экспорт не открыты.**
Их URL отсутствуют; наличие роли или свежей MFA не включает эти функции.
Движок попыток, XP, платежи и интеграция Frontend также не добавлены.

## Совместимость и миграция

Новая head — `0004_admin` после неизменённых 0001–0003. Добавлены:

- `admin_mfa_credentials`: encrypted secret, counter, credential epoch, rate-limit state;
- `admin_recovery_codes`: SHA-256 хэши случайных одноразовых 128-bit кодов, epoch, used_at;
- `admin_step_ups`: session/user composite FK, epoch, roles digest, verified/expires/revoked.
  Grant — временная составная запись сессии: её штатная TTL-очистка каскадно удаляет
  grant, сохраняя credential/recovery и append-only audit. Identity maintenance не менялся;
- nullable `content_sources.created_by` + FK/index и запрет creator=reviewer при
  заполненных полях. Старые источники получают NULL; авторство не выдумывается.

Контент, Identity, публичные DTO и данные исходного банка не переписываются.
10 legacy вопросов остаются draft. Опубликованные revisions/options и их pointers
сохраняют защиту 0003. Функция источника не заменяется, исходные миграции не правятся.
До явного upgrade новый `/ready` вернёт 503. Автомиграций при startup нет.

Запуск изолированной dev/test среды — по [README](README.md).
Для текущего API нужен настроенный Content cursor key из этапа 3a.
Дополнительно: `MEDEXA_MFA_ENCRYPTION_KEY` — отдельный Fernet key, например полученный
локально `Fernet.generate_key()` из cryptography. Не хранить его в Git, CI-логах,
истории команд или рядом с DB backup. Не переиспользовать bot/CSRF/cursor ключи;
конфигурация отвергает их точное совпадение. Пустой ключ отключает step-up (503),
а административные данные без серверного grant не выдаются (403).

## MFA: серверная модель доверия

- Выбран RFC 6238 TOTP: случайный secret 160 бит, SHA1/HMAC, 6 цифр, 30 секунд,
  окно ±1 time step. Требуется корректное UTC-время/NTP на сервере.
- Fernet authenticated encryption хранит secret в зашифрованном JSON, привязанном
  к user UUID. Перестановка ciphertext между пользователями/изменение токена
  не проходит проверку. Шифрование — cryptography, не собственный шифр.
- Последний принятый counter сохраняется в БД; такой же/более старый counter
  повторно не принимается, в том числе из параллельных запросов/другой сессии.
- 5 неверных кодов дают блокировку подтверждения на 5 минут. Счётчик общий для
  пользователя и переживает смену процесса/сессии. Ошибки возвращаются после
  коммита счётчика и audit: исключение с rollback здесь обошло бы rate limiter.
  Следующий запрос в блокировке получает 429/Retry-After:300.
- Grant хранится только на сервере и привязан к обычной сессии, user_id, версии
  credential и digest набора ролей. Нет MFA bearer, клиентского флага или доверия
  заголовку X-MFA-Verified. Grant не переносится в новый Telegram login/session.
- Срок ≤15 минут и не дольше idle/absolute expiry обычной сессии. GET не продлевает
  его. Сервер проверяет срок, future timestamp, revocation, credential epoch и роли
  при **каждом** административном чтении и изменении.
- Обычная cookie остаётся Secure/HttpOnly/SameSite=Lax; мутации требуют Origin,
  Fetch Metadata и session-bound CSRF. Именование cookie/Telegram HMAC не менялось.
- Исключение из step-up только для точного POST/DELETE `/admin/auth/step-up`:
  получение proof требует роли и CSRF; отозвать grant можно без свежего proof.
  Повторно использовать bootstrap permission на другом URL запрещено.
- Все остальные, ещё не реализованные привилегии (publish/import/roles/payments)
  остаются fail-closed даже при grant. Отдельного универсального bypass для admin нет.

TOTP подвержен phishing/real-time relay; это не WebAuthn. WebAuthn и организационная
политика управления устройствами не заявляются реализованными. Не использовать
этот development Backend как публичную production админку без инфраструктурного gate.

## Подключение и восстановление: только оператор

HTTP enrollment/recovery нет. Требуется доверенный оператор с доступом к новой
локальной среде и существующий активный пользователь, вошедший через Telegram,
с административной ролью. Используются существующие коды `content_editor`,
`content_reviewer` (медицинский reviewer), `admin`; billing_admin имеет только
право подтвердить MFA для будущего billing. Student/support не могут step-up.

Первый admin назначается прежней одноразовой командой Identity bootstrap по
проверенному числовому Telegram ID. HTTP выдача ролей в 3b.1 **не реализована**;
дополнительные назначения требуют отдельной контролируемой операторской процедуры.
Нельзя выдавать роли из username, пользовательского JSON или Telegram Premium.

В приватном интерактивном TTY, с конфигурацией новой локальной БД и отдельным ключом:

```sh
uv run --env-file .env --no-sync python -m app.admin.provision --telegram-user-id VERIFIED_ID --confirm
```

Оператор сверяет числовой ID вне API. CLI создаёт случайный secret, показывает
его **только в приватном TTY**, затем принимает TOTP через getpass. Секреты/OTP
не принимаются в argv. Перенаправление stdout/non-TTY запрещено. Не запускайте
команду в записываемой терминальной сессии, CI или общем screen recording.

После подтверждения и успешного DB commit CLI один раз показывает 10 recovery-кодов.
Сохранить в защищённом password manager отдельно от устройства MFA. В БД только
user-bound hash, старые коды не извлекаются API. Enrollment отзывает все обычные
сессии и step-up; нужно заново войти через Telegram и дождаться следующего TOTP
шага: код подключения уже использован.

Для восстановления в том же доверенном TTY:

```sh
uv run --env-file .env --no-sync python -m app.admin.provision --telegram-user-id VERIFIED_ID --recover --confirm
```

Нужны одноразовый recovery-код, новый случайный secret и новый TOTP. Все прежние
recovery-коды помечаются использованными/выведенными из обращения, credential epoch
увеличивается, сессии/grants отзываются. Повтор старого recovery-кода запрещён.
Медицинские данные не удаляются. Нет force-reset без recovery или публичного
отключения MFA; при утрате обоих факторов нужна отдельно утверждённая процедура
восстановления. Автоматическое шифрование новым master key/ротация всех credentials
не реализованы; backup ключа обязателен. Ручная смена env key без процедуры сделает
старые secrets недоступными для подтверждения.

## Административный API

Префикс `/api/v1/admin`. Общие JSON envelopes/ошибки/no-store прежние.

| Endpoint | Доступ / поведение |
|---|---|
| POST `/auth/step-up` | E/R/B/A + CSRF; `{code: "123456"}` → verified_at/expires_at, без secret/token |
| DELETE `/auth/step-up` | E/R/B/A + CSRF; idempotent 204, обычная сессия остаётся |
| GET/POST `/disciplines`; GET/PATCH/DELETE `/disciplines/{id}` | MFA; draft taxonomy |
| GET/POST `/topics`; GET/PATCH/DELETE `/topics/{id}` | MFA; реальные owner FK discipline/category |
| GET/POST `/test-definitions`; GET/PATCH/DELETE `/test-definitions/{id}` | MFA; duration/limit, draft only |
| GET/POST `/sources`; GET/PATCH/DELETE `/sources/{id}` | MFA; provenance/license draft, без approval |
| GET/POST `/questions`; GET `/questions/{id}` | MFA; manual draft/questions, current pointer не меняется |
| GET/POST `/questions/{id}/revisions`; GET/PATCH `/question-revisions/{id}` | MFA; новые редакции/редактирование own draft |

GET доступен E/R/A; запись — editor/admin. Reviewer здесь только читает для будущего
review workflow. Даже admin не может редактировать/архивировать published revision
или переключить current_revision_id. Для нового предложения по published question
создаётся новая draft revision, номер MAX+1, свежие option UUID. Старый pointer и
текст/ключи истории остаются прежними. Обычный Content API не выдаёт новый draft.

Editor читает/изменяет собственные drafts, видит published/withdrawn revisions и
approved published sources. Чужой draft/source без права reviewer/admin →404.
Reviewer читает все drafts; само наличие роли reviewer не даёт редактирование.
Admin может исправить чужой draft, но становится его новым автором; медицинские
approval поля всегда сбрасываются. На таксономию применяются общие staff permissions,
а не персональная ownership-модель. Вопросный текст не генерируется сервером.

В body нельзя передать status, created_by, medical_review_by, reviewed_at,
current_revision_id. Extra fields отвергаются. Один корректный key для single_choice,
явные boolean is_correct, 2–8 вариантов, уникальные коды A–H и UTF-8 лимиты обязательны.
Multiple choice допускается только как draft; публикация текущим клиентом запрещена.
Отсутствующая лицензия явно хранится NULL, не выдаётся за проверенную.

Каждая write транзакция проверяет `If-Match`, блокирует catalog_state и только затем
меняет сущность. Получите текущий `ETag: "content-N"` из административного GET/list.
Ответ write возвращает новый ETag. Token общий для каталога: изменение другого
объекта тоже может потребовать reload. Нет/неверный/stale If-Match →412; конфликт
FK/slug/external key →409, без raw SQL. Это optimistic concurrency, не auth-token.
PATCH в этой версии принимает **полное replacement body draft**, как POST; не merge
произвольных полей. DELETE только переводит draft в withdrawn, не физически удаляет.

Списки поддерживают query/cursor/limit 1–100. Используется существующий ContentReader,
нормализация, signed keyset cursor, catalog_version; admin scope дополнительно связан
с ролями и user. Изменение банка →409, неверный/чужой cursor →400. Данные тела/ключи
ответов доступны только MFA-подтверждённым staff. Логи не содержат query/body/OTP;
аудит содержит actor/action/target/request_id без копирования медицинского текста
или MFA secret. Content mutation и audit коммитятся атомарно.

HTTP JSON остаётся ограничен **32 KiB целиком**, как в Identity. Upload exception
для 10 MB не добавлен до защищённого streaming quarantine этапа 3b.2.

## Что будет в следующих PR

**3b.2 — staging/import, base 3b.1:** утверждённые versioned XLSX/DOCX-шаблоны §11;
закрытый upload/quarantine, SHA-256/magic/type/package checks; запрет XLS/DOC/XLSM,
макросов, external rels/embeds и формул (включая cached values); traversal/ZIP entries,
ZIP bomb/unpacked limits; DB jobs/leases/cancel/reclaim/retry и bounded subprocess;
строковый dry-run create/update/unchanged/conflict; безопасный CSV/XLSX report export.
Утверждённые первичные границы не меняются: файл 10 MB, unpacked 50 MB, 5000 строк,
60 секунд. Memory/ZIP-entry budget закрепить измерениями до открытия upload.
Негативные кейсы spoofing, bombs, formulas, timeout/OOM, cancel и worker restart
должны пройти на PostgreSQL 16. Никакого inline тяжёлого парсинга в HTTP.

**3b.3 — review/publish, base 3b.2:** immutable approval конкретного fingerprint,
reviewer != author/last editor, отдельные approve/publish шаги; source/license gate;
atomic batches ≤100, permanent row applied_revision_id и идемпотентность; partial
failure/applied/pending/failed status; повтор worker не дублирует revisions;
withdraw и audit восстановления pointer на допустимую approved revision.
Не меняются исторические attempts; exam-safe DTO продолжают исключать ключи.

Ни один из этих будущих endpoints не зарегистрирован в текущем router.

## Откат и безопасность эксплуатации

Предпочтителен forward fix. Destructive downgrade `0004_admin→0003_content` только
в изолированной новой БД после backup: он удаляет MFA credentials/grants/recovery
hashes и source ownership нового этапа, но сохраняет Content/Identity и audit.
Повторный upgrade не восстанавливает credentials/ownership автоматически.
Старый runtime 3a не знает новый admin router, но при фактическом rollback нельзя
оставлять 3b runtime с удалённой схемой. Требуются остановка нового API, проверка
backup/ключа и согласованная версия runtime+schema. Никакого `downgrade base` на
рабочей БД. Производственные DB-права/HTTPS/proxy/backup в этом PR не настраиваются.
