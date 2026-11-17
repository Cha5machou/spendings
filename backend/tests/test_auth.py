"""The auth dependency: disabled by default, fails closed when half configured, and only lets
verified, allow-listed e-mail addresses through. Token verification itself is replaced by a stub."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.config import settings


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()

    @app.get("/secret")
    def secret(user=Depends(auth.require_user)):
        return {"user": user}

    return TestClient(app)


def configure(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


def test_disabled_lets_everyone_in(client, monkeypatch):
    configure(monkeypatch, auth_enabled=False)
    assert client.get("/secret").json() == {"user": None}


def test_enabled_without_configuration_fails_closed(client, monkeypatch):
    configure(monkeypatch, auth_enabled=True, firebase_project_id=None, allowed_emails=[])
    assert client.get("/secret").status_code == 503


def test_missing_token_is_rejected(client, monkeypatch):
    configure(monkeypatch, auth_enabled=True, firebase_project_id="demo", allowed_emails=["me@example.com"])
    assert client.get("/secret").status_code == 401
    assert client.get("/secret", headers={"Authorization": "Basic abc"}).status_code == 401


def test_invalid_token_is_rejected(client, monkeypatch):
    configure(monkeypatch, auth_enabled=True, firebase_project_id="demo", allowed_emails=["me@example.com"])

    def reject(token):
        raise ValueError("bad signature")

    monkeypatch.setattr(auth, "verify_token", reject)
    assert client.get("/secret", headers={"Authorization": "Bearer nope"}).status_code == 401


@pytest.mark.parametrize("claims, status", [
    ({"email": "me@example.com", "email_verified": True}, 200),
    ({"email": "ME@Example.com", "email_verified": True}, 200),
    ({"email": "me@example.com", "email_verified": False}, 403),
    ({"email": "someone@else.com", "email_verified": True}, 403),
    ({}, 403),
])
def test_allow_list(client, monkeypatch, claims, status):
    configure(monkeypatch, auth_enabled=True, firebase_project_id="demo", allowed_emails=["me@example.com"])
    monkeypatch.setattr(auth, "verify_token", lambda token: claims)
    assert client.get("/secret", headers={"Authorization": "Bearer good"}).status_code == status
