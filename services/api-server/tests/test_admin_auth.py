"""Admin auth and credential masking tests."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api-server"))
sys.path.insert(0, str(ROOT / "packages" / "core"))


@pytest.fixture
def admin_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "admin123")
    monkeypatch.setattr(settings, "OPERATIONS_USERNAME", "ops")
    monkeypatch.setattr(settings, "OPERATIONS_PASSWORD", "ops123")
    monkeypatch.setattr(settings, "OPERATIONS_TOKEN", "test-ops-token")
    return settings


def test_authenticate_admin(admin_settings):
    from app.services.admin_auth import authenticate_admin, admin_token_for_context

    ctx = authenticate_admin("admin", "admin123")
    assert ctx is not None
    assert ctx.role == "admin"
    assert admin_token_for_context(ctx) == "test-admin-token"

    ops = authenticate_admin("ops", "ops123")
    assert ops is not None
    assert ops.role == "operations"

    assert authenticate_admin("admin", "wrong") is None


def test_resolve_admin_context_bearer_and_header(admin_settings):
    from app.services.admin_auth import resolve_admin_context

    assert resolve_admin_context("test-admin-token").role == "admin"
    assert resolve_admin_context("test-ops-token").role == "operations"
    assert resolve_admin_context("bad") is None


def test_admin_login_endpoint(admin_settings):
    from fastapi import FastAPI

    from app.routers.admin.auth import router as auth_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/admin")
    client = TestClient(app)
    bad = client.post("/admin/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/admin/login", json={"username": "admin", "password": "admin123"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["token"] == "test-admin-token"
    assert body["role"] == "admin"

    me = client.get("/admin/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "admin"

    me_header = client.get("/admin/me", headers={"X-Admin-Token": body["token"]})
    assert me_header.status_code == 200


def test_public_credential_row_masks_secrets():
    from app.services.credential_mask import public_credential_row

    cred = SimpleNamespace(
        id=uuid.uuid4(),
        broker="tiger",
        account_id="123456",
        label="main",
        config={"env": "production", "tiger_id": "999"},
        private_key_encrypted="encrypted-private-key-blob-value",
        secrets_encrypted="encrypted-secrets-blob",
    )
    row = public_credential_row(cred)
    assert row["has_private_key"] is True
    assert row["has_secrets"] is True
    assert "encrypted-private-key" not in str(row.get("key_hint", "")) or "••••" in row["key_hint"]
    assert "private_key_encrypted" not in row
    assert "secrets_encrypted" not in row


def test_admin_brokers_endpoint_uses_masked_credentials(admin_settings):
    """fetch_user_brokers must expose public_credential_row only (no ciphertext)."""
    import asyncio
    from unittest.mock import MagicMock

    from app.services.admin_user_detail import fetch_user_brokers
    from app.services.credential_mask import public_credential_row

    uid = uuid.uuid4()
    cred = SimpleNamespace(
        id=uuid.uuid4(),
        broker="tiger",
        account_id="acct",
        label="main",
        config={},
        private_key_encrypted="super-secret-key-material",
        secrets_encrypted="super-secret-secrets",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [cred]
    mock_db = AsyncMock()
    empty_bindings = MagicMock()
    empty_bindings.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(side_effect=[mock_result, empty_bindings])

    data = asyncio.run(fetch_user_brokers(mock_db, uid))
    assert len(data["credentials"]) == 1
    row = data["credentials"][0]
    assert row == public_credential_row(cred)
    assert "super-secret" not in str(row)
    assert "private_key_encrypted" not in row
    assert "secrets_encrypted" not in row


def test_admin_routers_do_not_import_decrypt():
    """Admin package must never import decrypt()."""
    import pathlib

    admin_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers" / "admin"
    offenders = []
    for path in admin_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "decrypt(" in text or "from app.services.crypto import decrypt" in text:
            offenders.append(path.name)
    assert offenders == [], f"admin routers must not decrypt: {offenders}"
