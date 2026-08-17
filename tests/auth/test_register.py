from __future__ import annotations

import uuid

import pytest


@pytest.mark.endpoint("POST /api/v1/auth/register")
async def test_register_returns_jwt_when_verification_disabled(api):
    email = f"t-{uuid.uuid4().hex}@example.com"
    resp = await api.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "test-password-1",
            "consent": True,
            "cross_border_consent": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == email

    # JWT боевой: закрытая ручка пускает без подтверждения почты.
    me = await api.get(
        "/api/user/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email
