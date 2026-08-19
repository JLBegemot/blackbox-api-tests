from __future__ import annotations

import pytest


@pytest.mark.endpoint("GET /api/user/personal-data")
async def test_personal_data_export_returns_user_data(api, user, auth):
    resp = await api.get("/api/user/personal-data", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["id"] == user["id"]
    assert body["user"]["email"] == user["email"]
    assert body["user"]["consent_given_at"] is not None
    # Свежий аккаунт: разделы есть, но пустые.
    assert body["resumes"] == []


@pytest.mark.endpoint("POST /api/user/revoke-consent")
async def test_revoke_consent_deletes_account(api, user, auth):
    resp = await api.post("/api/user/revoke-consent", headers=auth, json={"confirm": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    # Аккаунт удалён: JWT ещё валиден по подписи, но пользователя больше нет.
    me = await api.get("/api/user/me", headers=auth)
    assert me.status_code == 401, me.text

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 401, login.text


@pytest.mark.endpoint("GET /api/user/personal-data")
async def test_personal_data_export_is_repeatable(api, user, auth):
    """Экспорт — чистое чтение: повтор не меняет ни статус, ни тело."""

    bodies = []
    for _ in range(4):
        resp = await api.get("/api/user/personal-data", headers=auth)
        assert resp.status_code == 200, resp.text
        bodies.append(resp.json())

    assert all(body == bodies[0] for body in bodies[1:])
    assert bodies[0]["user"]["id"] == user["id"]


@pytest.mark.endpoint("DELETE /api/user/account")
async def test_account_deletion_is_irreversible(api, user, auth):
    """Первый DELETE удаляет аккаунт, повторные отдают 401.

    JWT остаётся валидным по подписи, поэтому повтор обязан упираться в
    «пользователя нет», а не удалять что-то ещё раз и не отдавать 200.
    """

    first = await api.request(
        "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
    )
    assert first.status_code == 200, first.text

    for _ in range(3):
        resp = await api.request(
            "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
        )
        assert resp.status_code == 401, resp.text

    # Данных удалённого аккаунта больше нет ни в одной пользовательской ручке.
    assert (await api.get("/api/user/me", headers=auth)).status_code == 401
    assert (await api.get("/api/user/personal-data", headers=auth)).status_code == 401

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 401, login.text


@pytest.mark.endpoint("GET /api/user/personal-data")
@pytest.mark.endpoint("POST /api/user/revoke-consent")
async def test_export_series_does_not_block_revoke_consent(api, auth):
    """Серия экспортов не мешает destructive-ручке отработать."""

    for _ in range(4):
        resp = await api.get("/api/user/personal-data", headers=auth)
        assert resp.status_code == 200, resp.text

    resp = await api.post("/api/user/revoke-consent", headers=auth, json={"confirm": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
