"""Контракт чувствительных ручек ``/api/user/*`` (152-ФЗ).

Покрыто: экспорт персональных данных, отзыв согласия с удалением аккаунта,
пер-JWT-бакеты лимитов (export 3/час, destructive 5/час) и их независимость.

⚠️ Не проверяется снаружи: IP из ``X-Forwarded-For`` в audit-log — записи
audit-log не отдаются ни одной ручкой, ассерт жил в белом ящике через БД.
В карте покрытия эти два кейса остаются «частично».
"""

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
    assert body["cvs"] == []


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
async def test_personal_data_export_bucket_exhausts_at_three(api, auth):
    # Бакет user.export — 3/час на JWT sub; четвёртый запрос — 429.
    for _ in range(3):
        resp = await api.get("/api/user/personal-data", headers=auth)
        assert resp.status_code == 200, resp.text

    blocked = await api.get("/api/user/personal-data", headers=auth)
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("Retry-After")
    assert int(blocked.headers["Retry-After"]) >= 1


@pytest.mark.endpoint("DELETE /api/user/account")
async def test_account_deletion_bucket_exhausts_at_five(api, auth):
    """Пять допущенных вызовов, шестой — 429.

    Первый вызов реально удаляет аккаунт, вызовы 2–5 получают 401 (пользователя
    нет), но каждый всё равно тратит слот бакета — лимит считается до хендлера.
    Шестой обязан быть 429, а не 401.
    """

    first = await api.request(
        "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
    )
    assert first.status_code == 200, first.text

    for _ in range(4):
        resp = await api.request(
            "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
        )
        assert resp.status_code == 401, resp.text

    blocked = await api.request(
        "DELETE", "/api/user/account", headers=auth, json={"confirm": True}
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("Retry-After")


@pytest.mark.endpoint("GET /api/user/personal-data")
@pytest.mark.endpoint("POST /api/user/revoke-consent")
async def test_destructive_and_export_buckets_are_independent(api, auth):
    """Выжигание export-бакета не трогает destructive-бакет.

    Разные бакеты — разные счётчики; тест ловит рефакторинг, случайно
    схлопнувший неймспейсы ``user.*`` в один.
    """

    for _ in range(3):
        resp = await api.get("/api/user/personal-data", headers=auth)
        assert resp.status_code == 200, resp.text
    assert (await api.get("/api/user/personal-data", headers=auth)).status_code == 429

    # Destructive-бакет обязан пустить первый же запрос.
    resp = await api.post("/api/user/revoke-consent", headers=auth, json={"confirm": True})
    assert resp.status_code == 200, resp.text
