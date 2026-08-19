# blackbox-api-tests

Чёрноящичные API-тесты бэкенда: HTTP-запросы к поднятому стенду, **ни одного импорта
модулей бэкенда**, никакого прямого доступа к БД/Redis/S3, никаких моков.

## Быстрый старт

**Стенд поднимается отдельно и этим репозиторием не управляется.** Тесты его
не запускают, не останавливают и не конфигурируют — они только ходят к нему
по HTTP.

```bash
# Стенд уже поднят и готов — прогнать тесты
uv run pytest -q

# Один файл / один тест
uv run pytest tests/auth/test_register.py -q
uv run pytest tests/auth/test_register.py::test_register_returns_jwt -q
```

Адрес стенда — `STAND_URL`, по умолчанию `http://localhost:8000`:

```bash
STAND_URL=http://stand.example:8080 uv run pytest -q
```

Тестам доступен только HTTP-интерфейс API. Постгрес, Redis и MinIO стенда для
них недоступны намеренно — как именно они спрятаны, дело того, кто поднимает
стенд.

Зависимости — dev-группа `pyproject.toml`. `asyncio_mode = "auto"`: тесты пишутся
как `async def` без декораторов.

## Как устроен набор

* **Детерминизм без моков** — его даёт конфигурация внешнего стенда: пустые
  LLM-ключи (агенты работают эвристикой, `model_used == "heuristic"`),
  `EMAIL_VERIFICATION_ENABLED=false` (register сразу возвращает JWT),
  зафиксированные лимиты и TTL.
* **Изоляция уникальностью, а не очисткой** — база между тестами не чистится,
  набор параллелится (`pytest -n`). Каждый тест получает своего пользователя
  `t-{uuid}@example.com` и свой IP в `X-Forwarded-For` (персональные бакеты
  rate-limit — без флаша Redis и без sleep).
* **Вся обвязка — `tests/conftest.py`**: фикстуры `api`, `user`, `auth`,
  `seed_resume`, `poll_until`, `sse`. Собственных клиентов и хелперов в
  тест-файлах нет.
* **Гейт маркеров по контракту** — каждый тест несёт
  `@pytest.mark.endpoint("METHOD /path")` и `@pytest.mark.case("TC-NNN")`.
  На коллекции операции сверяются со спекой стенда (офлайн — со снапшотом);
  незнакомая операция роняет коллекцию.

## Контракт

```bash
# Сверить live-спеку стенда со снапшотом contracts/openapi.json
python scripts/openapi_snapshot.py --check

# Принять дрейф осознанно (перезаписать снапшот)
python scripts/openapi_snapshot.py --dump
```

Новая ручка в API → сначала `--dump`, потом тесты на неё.

## Структура

```
contracts/   снапшот OpenAPI
tests/       auth/  user/  resumes/  ai/  legal/
scripts/     openapi_snapshot.py
```
