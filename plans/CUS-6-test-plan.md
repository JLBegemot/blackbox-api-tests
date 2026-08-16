# Тест-план: PATCH /api/user/me (CUS-6)

**Режим:** full · **Профиль:** http
· **Источник:** Linear CUS-6 + PR JLBegemot/cv-customs-webinar-version#1
(дифф: `.claude/tmp/CUS-6/backend.diff`, спека PR: `.claude/tmp/CUS-6/openapi.json`)
· **Контракт:** `contracts/openapi.json`

Ручка новая: до этой задачи `PATCH /api/user/me` не было ни в снапшоте,
ни на стенде, ни в тестах — режим `full`, вся ручка целиком.

Дельта контракта относительно снапшота: операция `PATCH /api/user/me`
и схема запроса `UpdateMeRequest` (`email: EmailStr|null`, `consent: bool|null`,
`cross_border_consent: bool|null` — все опциональны); ответ — существующий
`UserMeResponse`.

Rate-limit-зависимости у хендлера нет (по диффу PR) — профиль `ratelimit`
не применяется.

Согласованный скоуп: только CUS-6. Собственные тесты `POST /api/v1/auth/login`
не пишутся (решение пользователя на гейте); login используется в кейсах только
как оракул следствия «смена email применяется сразу».

### Новые тесты

| TC | Сценарий | Тип | Данные и запрос | Ожидаемый результат | Приоритет | Источник |
|---|---|---|---|---|---|---|
| TC-001 | Смена email применяется сразу | Positive | свежий пользователь; `PATCH {"email": <новый>}` | 200, `email` в ответе — новый; `POST /api/v1/auth/login` старым email → 401, новым → 200 | blocker | план |
| TC-002 | Email занят другим пользователем (case-insensitive) | Negative | два пользователя; PATCH на email второго в ДРУГОМ регистре | 409, `detail.code == "EMAIL_TAKEN"`; GET /me — email прежний; вход по прежнему email работает | critical | план |
| TC-003 | Свой email в другом регистре — no-op | Positive | `PATCH {"email": <свой email UPPERCASE>}` | 200, email в ответе и GET /me — в исходном регистре; вход по исходному работает | normal | код |
| TC-004 | Повторная выдача `consent: true` идемпотентна | Positive | пользователь (согласие выдано регистрацией — иначе register даёт 422); PATCH `{"consent": true}` дважды | 200 оба раза, `consent_given_at` не сдвигается относительно значения до PATCH | critical | план |
| TC-005 | Жизненный цикл `cross_border_consent` | Positive | регистрация в тесте с `cross_border_consent: false`; PATCH `true` → `true` → `false` | отметка появляется (ISO), повторный `true` её не сдвигает, `false` очищает в `null` | critical | план |
| TC-006 | `cross_border_consent: false` при пустой отметке | Positive | регистрация в тесте с `cross_border_consent: false`; PATCH `{"cross_border_consent": false}` | 200, `cross_border_consent_at` остаётся `null` | normal | код |
| TC-007 | Отзыв основного согласия через PATCH запрещён | Negative | пользователь с выданным согласием; PATCH `{"consent": false}` | 422, `detail.code == "CONSENT_REVOKE_FORBIDDEN"`, `detail.hint` содержит `/api/user/revoke-consent`; GET /me → 200, `consent_given_at` на месте | blocker | план |
| TC-008 | `consent: false` блокирует весь запрос, email не применяется | Negative | PATCH `{"consent": false, "email": <новый>}` | 422 `CONSENT_REVOKE_FORBIDDEN`; вход по старому email → 200 (смена не произошла) | critical | код |
| TC-009 | Тело без значимых полей | Negative | `PATCH {}` и `PATCH {"email": null, "consent": null, "cross_border_consent": null}` [@parametrize] | 422, `detail.code == "NOTHING_TO_UPDATE"` | blocker | план |
| TC-010 | Невалидное тело режется схемой | Negative | [@parametrize: `email: "not-an-email"`, `email: "u@x.test"` (special-use TLD), `consent: "yes"`] | 422 от Pydantic (`detail` — список с `loc`) | critical | контракт |
| TC-011 | Без токена | Negative | PATCH без `Authorization` | 401 | critical | инференс |
| TC-012 | Комбинированное обновление одним запросом | Positive | регистрация в тесте с `cross_border_consent: false`; PATCH `{"email": <новый>, "consent": true, "cross_border_consent": true}` | 200; в ответе новый email и обе отметки — непустые ISO-строки | normal | план |
| TC-013 | Email удалённого пользователя свободен | Positive | user2 удаляет аккаунт (`DELETE /api/user/account`, `confirm: true`); user1 PATCH на его email | 200; вход по этому email с паролем user1 → 200 | normal | код |

### Правки существующих тестов

| TC | Тест | Что добавить | Тип | Приоритет |
|---|---|---|---|---|
| — | нет | — | — | — |

### Кейсы со статусом ⏳ — заготовки

| TC | Сценарий | Причина блокировки | Что нужно для разблокировки |
|---|---|---|---|
| — | нет | — | — |

### Кейсы со статусом ✖ — в код не идут

| TC | Сценарий | Почему не пройдёт никто | Чем покрыто |
|---|---|---|---|
| ✖ | Записи `audit_log` (`email_changed`, `consent_granted`, `cross_border_consent_granted/revoked`) | API журнал не отдаёт ни одной ручкой (DB-003) | юниты бэкенда (`tests/api/test_user_account.py` в репозитории бэкенда) |
| ✖ | Первая выдача основного согласия через PATCH (`consent: true` при пустой `consent_given_at`) | Предусловие недостижимо: register требует `consent=true` — 422 «Consent … is required (152-FZ)», проверено пробным запросом к стенду | юниты бэкенда (`test_patch_me_grants_consent_once`, `make_user(consent=False)`) |

### Размещение

| Куда | Что |
|---|---|
| `tests/user/test_user_me_update.py` (новый файл, STRUCT-002) | TC-001…TC-013 |

### Инфраструктура

| Что нужно | Есть? | Где |
|---|---|---|
| HTTP-клиент, уникальный `X-Forwarded-For` | да | `api` (`tests/conftest.py`) |
| Свежий пользователь с токеном | да | `user` (`tests/conftest.py`) |
| Заголовок авторизации | да | `auth` (`tests/conftest.py`) |
| Второй пользователь в тесте | да | повторный register по образцу фикстуры `user` |

Дополнительно не покрыто (за скоупом, по решению пользователя в код не идёт):
собственные тесты `POST /api/v1/auth/login`; ассерты на `id`/`consent_given_at`/
`created_at` в существующем happy path `GET /api/user/me`.
