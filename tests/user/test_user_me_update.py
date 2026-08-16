"""Контракт ``PATCH /api/user/me`` — частичное обновление профиля (CUS-6).

Покрыто: смена email (применяется сразу и меняет идентичность входа,
занятость проверяется без учёта регистра, свой email в другом регистре —
no-op), идемпотентная выдача согласий с серверными таймстемпами, отзыв
трансграничного согласия, запрет отзыва основного согласия через PATCH
(для него есть ``POST /api/user/revoke-consent``), пустое и невалидное тело.

⚠️ Не проверяется снаружи: записи ``audit_log`` (``email_changed``,
``consent_granted``, ``cross_border_consent_*``) — журнал не отдаётся ни одной
ручкой; первая выдача основного согласия через PATCH — предусловие «пользователь
без ``consent_given_at``» недостижимо: register требует ``consent=true``.
Оба сценария покрыты юнитами в репозитории бэкенда.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest


def _fresh_email() -> str:
    return f"t-{uuid.uuid4().hex}@example.com"


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-001")
async def test_patch_me_changes_email_and_login_identity(api, user, auth):
    new_email = _fresh_email()

    resp = await api.patch("/api/user/me", headers=auth, json={"email": new_email})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == new_email

    # Смена применяется сразу: старый email больше не логинится, новый — да.
    old_login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert old_login.status_code == 401, old_login.text

    new_login = await api.post(
        "/api/v1/auth/login",
        json={"email": new_email, "password": user["password"]},
    )
    assert new_login.status_code == 200, new_login.text


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-002")
async def test_patch_me_rejects_taken_email_case_insensitive(api, user, auth):
    other_email = _fresh_email()
    other = await api.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "password": "test-password-1",
            "consent": True,
            "cross_border_consent": False,
        },
    )
    assert other.status_code == 200, other.text

    resp = await api.patch(
        "/api/user/me", headers=auth, json={"email": other_email.upper()}
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "EMAIL_TAKEN"

    # Email не изменился, вход по прежнему адресу работает.
    me = await api.get("/api/user/me", headers=auth)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == user["email"]

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200, login.text


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-003")
async def test_patch_me_same_email_different_case_is_noop(api, user, auth):
    resp = await api.patch(
        "/api/user/me", headers=auth, json={"email": user["email"].upper()}
    )
    assert resp.status_code == 200, resp.text
    # Регистр не считается изменением: email остаётся ровно как при регистрации.
    assert resp.json()["email"] == user["email"]

    me = await api.get("/api/user/me", headers=auth)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == user["email"]

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200, login.text


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-004")
async def test_patch_me_repeated_consent_grant_keeps_timestamp(api, user, auth):
    before = await api.get("/api/user/me", headers=auth)
    assert before.status_code == 200, before.text
    granted_at = before.json()["consent_given_at"]
    assert granted_at is not None

    for _ in range(2):
        resp = await api.patch("/api/user/me", headers=auth, json={"consent": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["consent_given_at"] == granted_at


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-005")
async def test_patch_me_cross_border_consent_lifecycle(api):
    reg = await api.post(
        "/api/v1/auth/register",
        json={
            "email": _fresh_email(),
            "password": "test-password-1",
            "consent": True,
            "cross_border_consent": False,
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    grant = await api.patch(
        "/api/user/me", headers=headers, json={"cross_border_consent": True}
    )
    assert grant.status_code == 200, grant.text
    granted_at = grant.json()["cross_border_consent_at"]
    assert granted_at is not None

    again = await api.patch(
        "/api/user/me", headers=headers, json={"cross_border_consent": True}
    )
    assert again.status_code == 200, again.text
    assert again.json()["cross_border_consent_at"] == granted_at

    revoke = await api.patch(
        "/api/user/me", headers=headers, json={"cross_border_consent": False}
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["cross_border_consent_at"] is None

    me = await api.get("/api/user/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["cross_border_consent_at"] is None


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-006")
async def test_patch_me_cross_border_false_on_empty_mark_is_noop(api):
    reg = await api.post(
        "/api/v1/auth/register",
        json={
            "email": _fresh_email(),
            "password": "test-password-1",
            "consent": True,
            "cross_border_consent": False,
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    resp = await api.patch(
        "/api/user/me", headers=headers, json={"cross_border_consent": False}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cross_border_consent_at"] is None


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-007")
async def test_patch_me_forbids_primary_consent_revocation(api, auth):
    resp = await api.patch("/api/user/me", headers=auth, json={"consent": False})
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "CONSENT_REVOKE_FORBIDDEN"
    assert "/api/user/revoke-consent" in detail["hint"]

    # Аккаунт жив, отметка согласия на месте.
    me = await api.get("/api/user/me", headers=auth)
    assert me.status_code == 200, me.text
    assert me.json()["consent_given_at"] is not None


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-008")
async def test_patch_me_consent_false_blocks_email_change(api, user, auth):
    resp = await api.patch(
        "/api/user/me",
        headers=auth,
        json={"consent": False, "email": _fresh_email()},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "CONSENT_REVOKE_FORBIDDEN"

    # Запрос отвергнут целиком: email не применён, вход по старому работает.
    me = await api.get("/api/user/me", headers=auth)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == user["email"]

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200, login.text


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-009")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty-body"),
        pytest.param(
            {"email": None, "consent": None, "cross_border_consent": None},
            id="all-fields-null",
        ),
    ],
)
async def test_patch_me_body_without_meaningful_fields_is_rejected(api, auth, body):
    resp = await api.patch("/api/user/me", headers=auth, json=body)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "NOTHING_TO_UPDATE"


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-010")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"email": "not-an-email"}, id="malformed-email"),
        pytest.param({"email": "user@invalid.test"}, id="special-use-tld"),
        # Pydantic v2 в lax-режиме приводит "yes"/"1" к True — непроходимое
        # значение для bool должно быть непреобразуемой строкой.
        pytest.param({"consent": "not-a-bool"}, id="consent-not-bool"),
    ],
)
async def test_patch_me_rejects_body_failing_schema(api, auth, body):
    resp = await api.patch("/api/user/me", headers=auth, json=body)
    assert resp.status_code == 422, resp.text
    # Ошибка именно схемы: detail — список Pydantic с указанием поля,
    # а не {"code": ...} из веток хендлера.
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and detail, resp.text
    assert detail[0]["loc"]


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-011")
async def test_patch_me_requires_auth(api):
    resp = await api.patch("/api/user/me", json={"email": _fresh_email()})
    assert resp.status_code == 401, resp.text


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-012")
async def test_patch_me_combined_update_applies_all_fields(api):
    reg = await api.post(
        "/api/v1/auth/register",
        json={
            "email": _fresh_email(),
            "password": "test-password-1",
            "consent": True,
            "cross_border_consent": False,
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    before = await api.get("/api/user/me", headers=headers)
    assert before.status_code == 200, before.text
    consent_at = before.json()["consent_given_at"]
    assert consent_at is not None

    new_email = _fresh_email()
    resp = await api.patch(
        "/api/user/me",
        headers=headers,
        json={"email": new_email, "consent": True, "cross_border_consent": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == new_email
    # Уже стоящую отметку основного согласия комбинированный запрос не сдвигает.
    assert body["consent_given_at"] == consent_at
    datetime.fromisoformat(body["cross_border_consent_at"])

    me = await api.get("/api/user/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == new_email
    assert me.json()["cross_border_consent_at"] == body["cross_border_consent_at"]


@pytest.mark.endpoint("PATCH /api/user/me")
@pytest.mark.case("TC-013")
async def test_patch_me_can_take_email_of_deleted_user(api, user, auth):
    departed_email = _fresh_email()
    # Пароль отличается от пароля user: логин по departed_email не должен
    # проходить ни с каким следом удалённого аккаунта.
    reg = await api.post(
        "/api/v1/auth/register",
        json={
            "email": departed_email,
            "password": "departed-password-9",
            "consent": True,
            "cross_border_consent": False,
        },
    )
    assert reg.status_code == 200, reg.text
    departed_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    gone = await api.request(
        "DELETE", "/api/user/account", headers=departed_headers, json={"confirm": True}
    )
    assert gone.status_code == 200, gone.text

    # Email удалённого аккаунта свободен: занимаем его сменой своего.
    resp = await api.patch(
        "/api/user/me", headers=auth, json={"email": departed_email}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == departed_email

    login = await api.post(
        "/api/v1/auth/login",
        json={"email": departed_email, "password": user["password"]},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == user["id"]
