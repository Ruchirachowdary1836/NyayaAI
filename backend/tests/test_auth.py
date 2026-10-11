from __future__ import annotations

import pytest
from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from conftest import make_admin, register

PROTECTED = [
    ("get", "/api/v1/auth/me"),
    ("post", "/api/v1/auth/logout"),
    ("get", "/api/v1/dashboard"),
    ("post", "/api/v1/search"),
    ("post", "/api/v1/compare"),
    ("post", "/api/v1/qa"),
    ("post", "/api/v1/qa/stream"),
    ("get", "/api/v1/documents"),
    ("get", "/api/v1/documents/C1"),
    ("get", "/api/v1/library/documents"),
    ("post", "/api/v1/library/search"),
    ("get", "/api/v1/experiments/runs"),
    ("get", "/api/v1/experiments/benchmarks"),
    ("post", "/api/v1/feedback"),
    ("get", "/api/v1/admin/overview"),
    ("get", "/api/v1/admin/users"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_endpoints_reject_missing_and_invalid_tokens(client, method, path) -> None:
    assert getattr(client, method)(path).status_code == 401
    invalid = getattr(client, method)(path, headers={"Authorization": "Bearer not-a-jwt"})
    assert invalid.status_code == 401


def test_register_login_session_and_profile(client) -> None:
    headers = register(client)
    profile = client.get("/api/v1/auth/me", headers=headers).json()
    assert profile["username"] == "researcher"
    assert profile["role"] == "user"
    assert profile["is_active"] is True
    assert profile["last_login_at"] is not None

    login = client.post(
        "/api/v1/auth/token", json={"username": "researcher", "password": "long-password"}
    )
    assert login.status_code == 200
    assert login.json()["expires_in"] == settings.jwt_access_token_expire_minutes * 60


def test_registration_validation_and_duplicates(client) -> None:
    register(client)
    duplicate = client.post(
        "/api/v1/auth/register", json={"username": "researcher", "password": "another-pass"}
    )
    assert duplicate.status_code == 409
    assert (
        client.post(
            "/api/v1/auth/register", json={"username": "bad name!", "password": "long-password"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/register", json={"username": "shortpw", "password": "short"}
        ).status_code
        == 422
    )


def test_wrong_password_and_unknown_user_are_indistinguishable(client) -> None:
    register(client)
    wrong = client.post(
        "/api/v1/auth/token", json={"username": "researcher", "password": "nope-nope"}
    )
    unknown = client.post("/api/v1/auth/token", json={"username": "ghost", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_logout_revokes_the_token(client) -> None:
    headers = register(client)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Session has been signed out"


def test_password_change_invalidates_all_existing_sessions(client) -> None:
    first = register(client)
    second_login = client.post(
        "/api/v1/auth/token", json={"username": "researcher", "password": "long-password"}
    )
    second = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    # Tokens carry whole-second issue times; make sure the change happens in a later second.
    import time

    time.sleep(1.1)
    update = client.put(
        "/api/v1/auth/me",
        headers=first,
        json={
            "current_password": "long-password",
            "username": "legal-researcher",
            "new_password": "new-long-password",
        },
    )
    assert update.status_code == 200
    new = {"Authorization": f"Bearer {update.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=new).json()["username"] == "legal-researcher"
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 401
    wrong = client.put(
        "/api/v1/auth/me",
        headers=new,
        json={"current_password": "wrong-password", "username": "legal-researcher"},
    )
    assert wrong.status_code == 401


def test_profile_update_rejects_taken_username(client) -> None:
    register(client, "first-user")
    headers = register(client, "second-user")
    response = client.put(
        "/api/v1/auth/me",
        headers=headers,
        json={"current_password": "long-password", "username": "first-user"},
    )
    assert response.status_code == 409


def test_expired_and_forged_tokens_are_rejected(client) -> None:
    register(client)
    expired = create_access_token("researcher", "user", expires_delta=-1)
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code
        == 401
    )
    # A token claiming the admin role for a regular account must not grant admin access.
    forged = create_access_token("researcher", "admin")
    response = client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_disabled_accounts_cannot_sign_in_and_lose_sessions(client) -> None:
    user_headers = register(client)
    admin = make_admin(client)
    import time

    time.sleep(1.1)
    assert (
        client.patch(
            "/api/v1/admin/users/researcher", headers=admin, json={"is_active": False}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 401
    login = client.post(
        "/api/v1/auth/token", json={"username": "researcher", "password": "long-password"}
    )
    assert login.status_code == 401


def test_authentication_endpoints_are_rate_limited(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 3)
    statuses = [
        client.post(
            "/api/v1/auth/token", json={"username": "ghost", "password": "whatever-1"}
        ).status_code
        for _ in range(4)
    ]
    assert statuses == [401, 401, 401, 429]
