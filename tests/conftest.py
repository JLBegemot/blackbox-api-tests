from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STAND_URL = os.environ.get("STAND_URL", "http://localhost:8000").rstrip("/")
SPEC_SNAPSHOT = REPO_ROOT / "contracts" / "openapi.json"

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


# ---------------------------------------------------------------------------
# Гейт маркеров endpoint по спеке
# ---------------------------------------------------------------------------


def _load_spec() -> dict:
    try:
        with urllib.request.urlopen(f"{STAND_URL}/openapi.json", timeout=3) as resp:
            return json.load(resp)
    except OSError:
        # Стенд не поднят (коллекция офлайн) — сверяемся со снапшотом.
        return json.loads(SPEC_SNAPSHOT.read_text(encoding="utf-8"))


def _operations(spec: dict) -> set[str]:
    return {
        f"{method.upper()} {path}"
        for path, item in spec.get("paths", {}).items()
        for method in item
        if method in _HTTP_METHODS
    }


def pytest_collection_modifyitems(config, items):
    known = _operations(_load_spec())
    unknown: list[str] = []
    for item in items:
        for mark in item.iter_markers("endpoint"):
            op = " ".join(str(mark.args[0]).split())
            if op not in known:
                unknown.append(f"  {item.nodeid}: '{op}'")
    if unknown:
        raise pytest.UsageError(
            "маркер endpoint ссылается на операции, которых нет в контракте:\n"
            + "\n".join(unknown)
            + "\nНовая ручка → обнови снапшот: python scripts/openapi_snapshot.py --dump"
        )


# ---------------------------------------------------------------------------
# HTTP-клиент
# ---------------------------------------------------------------------------


@pytest.fixture
def client_ip() -> str:
    """Уникальный клиентский IP на тест.

    Стенд читает клиентский адрес из первого хопа ``X-Forwarded-For`` и пишет
    его в серверное состояние (журналы, счётчики). Уникальный IP не даёт
    параллельным тестам связываться через это состояние (RATE-001).
    """

    a, b, c = uuid.uuid4().bytes[:3]
    return f"10.{a}.{b}.{c}"


@pytest.fixture
async def api(client_ip):
    """``httpx.AsyncClient`` на стенд с уникальным ``X-Forwarded-For``."""

    async with httpx.AsyncClient(
        base_url=STAND_URL,
        headers={"X-Forwarded-For": client_ip},
        timeout=httpx.Timeout(10.0, read=30.0),
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Пользователь и авторизация
# ---------------------------------------------------------------------------


@pytest.fixture
async def user(api) -> dict:
    """Свежий пользователь: ``{"email", "password", "id", "token"}``.

    Стенд живёт с ``EMAIL_VERIFICATION_ENABLED=false``, поэтому register
    сразу возвращает 200 с JWT — второй запрос не нужен.
    """

    email = f"t-{uuid.uuid4().hex}@example.com"
    password = "test-password-1"
    resp = await api.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "consent": True,
            "cross_border_consent": True,
        },
    )
    assert resp.status_code == 200, (
        f"register вернул {resp.status_code}: {resp.text} — стенд поднят "
        "с EMAIL_VERIFICATION_ENABLED=false?"
    )
    body = resp.json()
    return {
        "email": email,
        "password": password,
        "id": body["user"]["id"],
        "token": body["access_token"],
    }


@pytest.fixture
def auth(user) -> dict:
    """Заголовок авторизации свежего пользователя.

    Отдельный логин — только там, где логин и есть предмет теста.
    """

    return {"Authorization": f"Bearer {user['token']}"}


# ---------------------------------------------------------------------------
# Сидинг данных — только через API
# ---------------------------------------------------------------------------

_DEFAULT_RESUME_CONTENT = {
    "schemaVersion": 1,
    "name": "Тест Тестовый",
    "headline": "QA engineer",
    "summary": "Seed resume for API tests.",
    "contacts": {"email": "seed@example.com"},
    "skills": ["python", "pytest"],
    "experience": [],
    "education": [],
}


@pytest.fixture
def seed_resume(api, auth):
    """Фабрика резюме: ``await seed_resume()`` → JSON ``ResumeDetail``.

    Сидинг одним ``POST /api/v1/resumes`` — ручка принимает опциональный
    ``content`` и сразу создаёт первую версию, upload и PDF не нужны.
    """

    async def _seed(*, title: str = "Test resume", content: dict | None = None) -> dict:
        resp = await api.post(
            "/api/v1/resumes",
            json={"title": title, "content": content or _DEFAULT_RESUME_CONTENT},
            headers=auth,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _seed


# ---------------------------------------------------------------------------
# Ожидания: фоновые задачи и SSE
# ---------------------------------------------------------------------------


@pytest.fixture
def poll_until(api):
    """Опрос ``GET url`` до целевого статуса с дедлайном.

    ``await poll_until("/api/v1/ai/analyze/{id}", headers=auth)`` → финальное
    тело ответа. По умолчанию ждёт ``status == "done"`` и падает, если задача
    ушла в ``error`` или дедлайн вышел. Никаких ``sleep`` без дедлайна.
    """

    async def _poll(
        url: str,
        *,
        headers: dict | None = None,
        done: str = "done",
        error: str = "error",
        timeout_s: float = 60.0,
        interval_s: float = 0.5,
    ) -> dict:
        deadline = time.monotonic() + timeout_s
        last: dict = {}
        while time.monotonic() < deadline:
            resp = await api.get(url, headers=headers)
            assert resp.status_code == 200, resp.text
            last = resp.json()
            status = last.get("status")
            if status == done:
                return last
            assert status != error, f"задача упала: {last}"
            await asyncio.sleep(interval_s)
        raise AssertionError(f"не дождались status={done!r} за {timeout_s}s, последнее: {last}")

    return _poll


@pytest.fixture
def sse(api):
    """Чтение ``text/event-stream`` с дедлайном.

    ``await sse(url, headers=auth)`` → список событий ``{"event", "data"}``
    (``data`` распарсен из JSON, если это JSON). Поток читается до закрытия
    сервером либо до ``max_events``; на дедлайне — AssertionError, бесконечное
    чтение запрещено.
    """

    async def _consume(
        url: str,
        *,
        headers: dict | None = None,
        timeout_s: float = 60.0,
        max_events: int = 200,
    ) -> list[dict]:
        events: list[dict] = []
        current: dict = {}

        async def _read() -> None:
            async with api.stream("GET", url, headers=headers) as resp:
                assert resp.status_code == 200, await resp.aread()
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current["event"] = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        raw = line.split(":", 1)[1].strip()
                        try:
                            current["data"] = json.loads(raw)
                        except ValueError:
                            current["data"] = raw
                    elif not line and current:
                        events.append(dict(current))
                        current.clear()
                        if len(events) >= max_events:
                            return

        try:
            await asyncio.wait_for(_read(), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise AssertionError(
                f"SSE-поток {url} не закрылся за {timeout_s}s; получено {len(events)} событий: {events[-3:]}"
            )
        return events

    return _consume
