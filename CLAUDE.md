# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Чёрноящичные API-тесты бэкенда: тесты — HTTP-клиенты к стенду, поднятому **снаружи и вне этого репозитория**. Ни одного импорта модулей бэкенда, никакого доступа к БД/Redis/S3, никаких моков. Прод-код бэкенда живёт в отдельном репозитории и здесь не редактируется никогда.

**Единственный источник правил тестов — `docs/test-rules.md`** (семейства ID: STAND, STRUCT, MARK, FIXT, DB, AUTH, RATE, JOB, SSE, ASSERT, RED, FORBID). Прочитай его перед написанием или ревью любого теста. Дублировать правила здесь и в промптах агентов запрещено — ссылайся на ID.

## Команды

```bash
# Прогон (стенд уже должен быть поднят; адрес — STAND_URL, дефолт http://localhost:8000)
uv run pytest -q
STAND_URL=http://stand.example:8080 uv run pytest -q

# Параллельный прогон (pytest-xdist в dev-группе)
uv run pytest -n auto -q

# Один файл / один тест
uv run pytest tests/auth/test_register.py -q
uv run pytest tests/auth/test_register.py::test_register_returns_jwt_when_verification_disabled -q

# Дрейф контракта: сверить live-спеку стенда со снапшотом contracts/openapi.json
uv run python scripts/openapi_snapshot.py --check
# Принять дрейф осознанно (перезаписать снапшот)
uv run python scripts/openapi_snapshot.py --dump

# Валидация cases.yaml (шаг пайплайна /api-tests, до генерации тестов)
uv run python scripts/validate_cases.py .claude/tmp/<id>/cases.yaml

# Формат и линт (то же, что дёргает хук на запись .py)
uv run ruff format . && uv run ruff check --fix .
```

`scripts/openapi_snapshot.py` намеренно stdlib-only, поэтому работает и как `python3 scripts/openapi_snapshot.py --check` — без окружения. Если сломался `.venv`, чинится `uv sync --reinstall`.

Зависимости — только dev-группа `pyproject.toml` (pytest, pytest-asyncio, pytest-xdist, httpx, pyotp, reportlab, pyyaml, ruff). `asyncio_mode = "auto"` — тесты пишутся как `async def` без декораторов.

## Архитектура

**Детерминизм без моков.** В чёрном ящике подменить зависимости нельзя — детерминизм даёт конфигурация внешнего стенда, которая живёт вместе с ним и не правится отсюда. Ключевые следствия: register сразу возвращает JWT (`EMAIL_VERIFICATION_ENABLED=false`), LLM-агенты работают эвристикой (пустые API-ключи), TTL и прочие пороги берутся из конфигурации стенда, а не из дефолтов бэкенда. Сервисного лимитера запросов на стенде нет (RATE-003).

**Что стенд отдаёт — решает контракт, а не этот файл.** Набор ручек и фича-флаги проверяются по `contracts/openapi.json` (или live-спеке), а не по памяти: `jq -r '.paths | keys[]' contracts/openapi.json` (STAND-004).

**Изоляция уникальностью, а не очисткой.** База между тестами не чистится; набор параллелизуем (`uv run pytest -n auto`). Каждый тест получает своего пользователя и свой IP в `X-Forwarded-For` (DB-002, RATE-001, RATE-002).

**Вся обвязка — `tests/conftest.py`**; собственные клиенты и хелперы в тест-файлах запрещены (FIXT-001). Состав фикстур и их назначение — FIXT-002, здесь не дублируются.

**Гейт маркеров по контракту.** Каждый тест несёт `@pytest.mark.endpoint("METHOD /path")`; на коллекции `conftest.py` сверяет операцию со спекой и роняет коллекцию на незнакомой (MARK-001).

**Раскладка** — по областям фич, `tests/<область>/test_<feature>.py`; каталог заводится вместе с первым тестом в нём (STRUCT-001, STRUCT-002).

## Пайплайн /api-tests

Скилл `/api-tests` (`.claude/skills/api-tests/`) — оркестратор «требования → согласованный с пользователем `cases.yaml` → генерация → ревью → MR». Сабагенты: `contract-explorer` (выжимка контракта и существующего покрытия), `test-writer` (один агент на целевой файл, только по утверждённому плану), `test-reviewer` (прогон и находки со ссылками на ID правил). Рабочие файлы задачи — `.claude/tmp/<id>/`, в коммит не идут. Чекаут бэкенда (`BACKEND_REPO`) — справочный источник фактических кодов ошибок; без него выводы помечаются `[инференс]`. Скилл `/ship` — ветка, коммит, пуш, текст MR.

Скоуп записи пайплайна (`tests/`, `plans/`, `docs/`, `.claude/tmp/`; `contracts/`, `scripts/` и конфигурация стенда — нет) держится правилом FORBID-011, а не технической блокировкой.

Технические ограничения в `.claude/settings.json` — отдельно от правил: хук `PostToolUse` на запись `.py` гоняет `ruff check --fix` и `ruff format` (`.claude/hooks/format-python.sh`), хук `PreToolUse` на `mcp__github__*` / `mcp__linear__*` пропускает только белый список инструментов (`.claude/hooks/guard-mcp-tools.sh`), плюс список `permissions.deny`. `.claude/settings.local.json` намеренно закрыт на чтение — `BACKEND_REPO` оттуда приходит через окружение.

## Красный тест

Красный тест не «зеленится» правкой бэкенда, конфигурации стенда или подгонкой ассерта: это вопрос «дефект сервиса или неверная предпосылка», и решает его пользователь. Развилка и то, как подтверждённый дефект всё-таки уезжает в MR, — RED-001…RED-003.
