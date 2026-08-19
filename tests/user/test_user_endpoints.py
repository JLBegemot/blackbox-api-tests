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


@pytest.mark.endpoint("DELETE /api/user/account")
async def test_delete_account_removes_user(api, user, auth):
    """Удаление аккаунта: ручка отвечает 200, пользователя больше нет.

    Повторный вызов тем же JWT — 401: подпись ещё валидна, но субъекта токена
    в базе уже нет.
    """

    resp = await api.request(
        "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
    )
    assert resp.status_code == 200, resp.text

    me = await api.get("/api/user/me", headers=auth)
    assert me.status_code == 401, me.text

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 401, login.text

    repeat = await api.request(
        "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
    )
    assert repeat.status_code == 401, repeat.text


@pytest.mark.endpoint("GET /api/user/personal-data")
async def test_personal_data_export_is_repeatable(api, auth):
    """Экспорт персональных данных не расходуется: подряд идущие вызовы — 200.

    Раньше здесь проверялся бакет ``user.export`` (3/час, четвёртый вызов 429);
    лимитер убран из сервиса, и тест сторожит обратное — что повторный экспорт
    остаётся доступным.
    """

    for _ in range(4):
        resp = await api.get("/api/user/personal-data", headers=auth)
        assert resp.status_code == 200, resp.text
