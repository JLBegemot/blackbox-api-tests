"""Сброс пароля: негативы и контракт без почтового ящика.

Приёмника почты на стенде нет (план 08 §2.5) — happy path сброса
(токен из письма меняет пароль, одноразовость токена) снаружи непроверяем
и в карте покрытия навсегда помечен ⚠️. Здесь — то, что живёт без письма:
молчаливый 202 на неизвестный e-mail и 400-ветки confirm.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.endpoint("POST /api/v1/auth/password/reset/request")
async def test_reset_request_is_202_for_unknown_email(api):
    # Валидный, но незарегистрированный адрес (uuid гарантирует отсутствие).
    resp = await api.post(
        "/api/v1/auth/password/reset/request",
        json={"email": f"nobody-{uuid.uuid4().hex}@example.com"},
    )
    # Молчаливый 202: существование аккаунта не раскрывается.
    assert resp.status_code == 202, resp.text


@pytest.mark.endpoint("POST /api/v1/auth/password/reset/confirm")
async def test_reset_confirm_rejects_unknown_token(api, user):
    resp = await api.post(
        f"/api/v1/auth/password/reset/confirm?email={user['email']}",
        json={"token": "x" * 32, "new_password": "whatever-new-1"},
    )
    assert resp.status_code == 400, resp.text

    # Пароль не изменился — старый всё ещё логинит.
    login = await api.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200, login.text


@pytest.mark.endpoint("POST /api/v1/auth/password/reset/confirm")
async def test_reset_confirm_requires_email(api):
    # Токен ≥16 символов, чтобы пройти pydantic-схему и попасть в ветку
    # хендлера «нет e-mail → 400», а не в 422 на теле запроса.
    resp = await api.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": "x" * 16, "new_password": "whatever-new-1"},
    )
    assert resp.status_code == 400, resp.text
