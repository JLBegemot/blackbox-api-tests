# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Чёрноящичные API-тесты бэкенда: тесты — HTTP-клиенты к стенду, поднятому **снаружи и вне этого репозитория**. Ни одного импорта модулей бэкенда, никакого доступа к БД/Redis/S3, никаких моков. Прод-код бэкенда живёт в отдельном репозитории и здесь не редактируется никогда.

**Единственный источник правил тестов — `docs/test-rules.md`** (правила с ID: STAND-*, STRUCT-*, FIXT-*, DB-*, AUTH-*, RATE-*, JOB-*, SSE-*, ASSERT-*, FORBID-*). Прочитай его перед написанием или ревью любого теста. Дублировать правила в других файлах запрещено — ссылайся на ID.

## Команды

```bash
# Прогон (стенд уже должен быть поднят; адрес — STAND_URL, дефолт http://localhost:8000)
uv run pytest -q
STAND_URL=http://stand.example:8080 uv run pytest -q

# Один файл / один тест
uv run pytest tests/auth/test_register.py -q
uv run pytest tests/auth/test_register.py::test_register_returns_jwt -q

# Дрейф контракта: сверить live-спеку стенда со снапшотом contracts/openapi.json
python scripts/openapi_snapshot.py --check
# Принять дрейф осознанно (перезаписать снапшот)
python scripts/openapi_snapshot.py --dump

# Валидация cases.yaml (шаг пайплайна /api-tests, до генерации тестов)
uv run python scripts/validate_cases.py .claude/tmp/<id>/cases.yaml
```

Если `uv run pytest` не работает на машине — запасной вариант `python -m pytest` из локального venv.

Зависимости — только dev-группа `pyproject.toml` (pytest, pytest-asyncio, httpx, pyotp, reportlab, pyyaml). `asyncio_mode = "auto"` — тесты пишутся как `async def` без декораторов.

## Архитектура

**Детерминизм без моков.** В чёрном ящике подменить зависимости нельзя — детерминизм даёт конфигурация внешнего стенда, которая живёт вместе с ним и не правится отсюда. Ключевые следствия: register сразу возвращает JWT (`EMAIL_VERIFICATION_ENABLED=false`), LLM-агенты работают эвристикой (пустые API-ключи, тесты ассертят `model_used == "heuristic"`), лимиты и TTL берутся из конфигурации стенда, а не из дефолтов бэкенда.

**Изоляция уникальностью, а не очисткой.** База между тестами не чистится; набор параллелизуем (`pytest -n`). Каждый тест получает своего пользователя `t-{uuid}@example.com` и свой IP в `X-Forwarded-For` — параллельные тесты не связываются через серверное состояние (RATE-001, RATE-002).

**Вся обвязка — `tests/conftest.py`**; собственные клиенты/хелперы в тест-файлах запрещены (FIXT-001). Фикстуры: `api` (httpx-клиент с уникальным IP), `user` (регистрация → email/password/id/token), `auth` (заголовок Authorization), `seed_resume` (фабрика резюме через API), `poll_until` (опрос фоновой задачи с дедлайном), `sse` (чтение event-stream с дедлайном и лимитом событий).

**Гейт маркеров по контракту.** Каждый тест несёт маркеры `@pytest.mark.endpoint("METHOD /path")` и `@pytest.mark.case("TC-NNN")`. На коллекции `conftest.py` сверяет операции из `endpoint` со спекой (live со стенда, офлайн — снапшот `contracts/openapi.json`); незнакомая операция роняет коллекцию. Новая ручка → сначала `python scripts/openapi_snapshot.py --dump`.

**Раскладка** — по фичам: `tests/auth/`, `tests/user/`, `tests/resumes/`, `tests/ai/`, `tests/legal/`; файл на фичу, не на роутер (STRUCT-002).

## Пайплайн /api-tests

Скилл `/api-tests` (`.claude/skills/api-tests/`) — оркестратор «требования → согласованный с пользователем `cases.yaml` → генерация → ревью → MR». Сабагенты: `contract-explorer` (выжимка контракта и существующего покрытия), `test-writer` (один агент на целевой файл, только по утверждённому плану), `test-reviewer` (прогон и находки со ссылками на ID правил). Рабочие файлы задачи — `.claude/tmp/<id>/`. Чекаут бэкенда (`BACKEND_REPO`, обычно в `.claude/settings.local.json`) — справочный источник фактических кодов ошибок; без него выводы помечаются `[инференс]`. Скилл `/ship` — ветка, коммит, пуш, текст MR.

Хуки (`.claude/settings.json`): каждый записанный `.py` автоматически форматируется `ruff format`. Ограничение «во время пайплайна писать только под `tests/`, `plans/`, `docs/`, `.claude/tmp/`, конфигурацию стенда не трогать» держится правилом FORBID-010 (`docs/test-rules.md`), а не технической блокировкой.

## Красный тест

Красный тест не «зеленится» правкой бэкенда, конфигурации стенда или подгонкой ассерта. Это всегда вопрос «дефект сервиса или неверная предпосылка теста», и решает его пользователь (FORBID-010).
