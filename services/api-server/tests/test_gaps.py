"""Tests for FCM / updater / inbound / geoip utilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api-server"))
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "clients" / "relay-agent"))


def test_updater_is_newer():
    from sigtrades_agent.updater import is_newer

    assert is_newer("1.2.0", "1.1.9")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("0.9", "1.0")


def test_updater_sha256_verify(tmp_path):
    from sigtrades_agent.updater import _verify_sha256

    p = tmp_path / "bin"
    p.write_bytes(b"hello agent")
    import hashlib
    digest = hashlib.sha256(b"hello agent").hexdigest()
    assert _verify_sha256(p, digest)
    assert not _verify_sha256(p, "bad")


def test_inbound_verify_dev_bypass(monkeypatch):
    from app.config import settings
    from app.services.inbound_mail_service import verify_resend_webhook_payload

    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_INBOUND_WEBHOOK", True)
    payload = '{"type":"email.received","data":{"email_id":"abc"}}'
    out = verify_resend_webhook_payload(payload, None, None, None)
    assert out["type"] == "email.received"


def test_inbound_verify_requires_secret(monkeypatch):
    from app.config import settings
    from app.services.inbound_mail_service import verify_resend_webhook_payload

    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_INBOUND_WEBHOOK", False)
    with pytest.raises(ValueError, match="RESEND_WEBHOOK_SECRET"):
        verify_resend_webhook_payload("{}", None, None, None)


def test_geoip_private_ip_skipped():
    from app.services.geoip_service import country_and_city_from_ip

    assert country_and_city_from_ip("127.0.0.1") == (None, None)
    assert country_and_city_from_ip("10.0.0.1") == (None, None)


def test_fcm_enabled_without_credentials(monkeypatch):
    from app.config import settings
    from app.services.fcm_service import fcm_enabled

    monkeypatch.setattr(settings, "FCM_PROJECT_ID", "")
    monkeypatch.setattr(settings, "FCM_CREDENTIALS_JSON", "")
    monkeypatch.setattr(settings, "FCM_CREDENTIALS_PATH", "")
    assert not fcm_enabled()


def test_build_reply_subject():
    from app.services.inbound_mail_service import build_reply_subject

    assert build_reply_subject("Hello") == "Re: Hello"
    assert build_reply_subject("Re: Hello") == "Re: Hello"


def test_inbound_recipient_domain_allowlist():
    from app.services.inbound_mail_service import is_allowed_inbound_recipient

    assert is_allowed_inbound_recipient(["team@sigtrades.com"])
    assert is_allowed_inbound_recipient(["Support <support@sigtrades.com>"])
    assert is_allowed_inbound_recipient(cc_list=["ops@mail.sigtrades.com"])
    assert not is_allowed_inbound_recipient(["user@gmail.com"])
    assert not is_allowed_inbound_recipient(["evil@sigtrades.com.evil.com"])
    assert not is_allowed_inbound_recipient([])


def test_fcm_access_token_failure_graceful(monkeypatch):
    import asyncio

    from app.services import fcm_service

    monkeypatch.setattr(fcm_service, "fcm_enabled", lambda: True)

    def _boom():
        raise RuntimeError("refresh failed")

    monkeypatch.setattr(fcm_service, "_refresh_access_token_sync", _boom)
    monkeypatch.setattr(fcm_service, "_cached_token", None)
    monkeypatch.setattr(fcm_service, "_token_expiry", None)
    token = asyncio.run(fcm_service._access_token())
    assert token is None


def test_idem_key_scoped_by_user():
    from app.services.redis_client import idem_key

    k1 = idem_key("src", "sig", "acct", user_id="u1")
    k2 = idem_key("src", "sig", "acct", user_id="u2")
    assert k1 != k2
    assert "u1" in k1 and "u2" in k2


def test_validate_production_secrets_rejects_defaults(monkeypatch):
    from app.config import Settings, validate_production_secrets

    s = Settings()
    monkeypatch.setattr(s, "APP_ENV", "production")
    with pytest.raises(RuntimeError, match="拒绝启动"):
        validate_production_secrets(s)


def test_validate_production_secrets_dev_noop():
    from app.config import Settings, validate_production_secrets

    s = Settings()  # APP_ENV=development by default
    validate_production_secrets(s)  # should not raise


def test_rate_limit_local_blocks_after_limit():
    import asyncio

    from app.services import rate_limit as rl

    rl._local.clear()
    allowed = [rl._allow_local("rl:test:ip", limit=3, window=60) for _ in range(5)]
    assert allowed == [True, True, True, False, False]


def test_report_detail_formats_fill_and_error():
    from app.routers.internal import ExecutionReportRequest, _report_detail

    req = ExecutionReportRequest(
        signal_id="s", source_id="src", broker="tiger", status="FILLED",
        fill_price=12.5, order_id="o1", attempt=2,
    )
    detail = _report_detail(req)
    assert "fill=12.5" in detail and "order=o1" in detail and "attempt=2" in detail


def test_execution_report_data_has_realized_pnl():
    from sigtrades_core.execution.core import ExecutionReportData

    rpt = ExecutionReportData(
        signal_id="s", source_id="src", broker="tiger", status="FILLED", realized_pnl=-42.0,
    )
    assert rpt.to_dict()["realized_pnl"] == -42.0


def _load_ingest_webhook():
    import importlib.util

    path = ROOT / "services" / "ingest" / "app" / "connectors" / "webhook.py"
    spec = importlib.util.spec_from_file_location("ingest_webhook", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_webhook_hmac_production_requires_secret():
    verify_hmac = _load_ingest_webhook().verify_hmac
    assert not verify_hmac(b"{}", None, None, require_secret=True)
    assert verify_hmac(b"{}", None, None, require_secret=False)


def test_webhook_hmac_with_secret_requires_signature():
    verify_hmac = _load_ingest_webhook().verify_hmac
    assert not verify_hmac(b"{}", None, "secret", require_secret=False)
    assert verify_hmac(b"{}", "bad", "secret", require_secret=False) is False


def test_tokens_include_token_version():
    import uuid

    from app.models import User
    from app.services.auth_service import _tokens

    user = User(id=uuid.uuid4(), email="t@e.com", token_version=3)
    access, refresh = _tokens(user)
    from app.security import decode_token

    ap = decode_token(access, "access")
    rp = decode_token(refresh, "refresh")
    assert ap["tv"] == 3
    assert rp["tv"] == 3


def test_in_flight_statuses_defined():
    from app.routers.internal import IN_FLIGHT_STATUSES, TERMINAL_STATUSES

    assert "ROUTING" in IN_FLIGHT_STATUSES
    assert "protective_failed" in TERMINAL_STATUSES


def test_format_et_and_day_boundary():
    from datetime import datetime, timezone

    from app.utils.datetime import et_day_start_utc, format_et

    # 2026-06-07 03:30 UTC = 2026-06-06 23:30 ET (still previous ET day)
    dt = datetime(2026, 6, 7, 3, 30, tzinfo=timezone.utc)
    assert format_et(dt) == "2026-06-06 23:30:00 ET"

    start = et_day_start_utc(dt)
    assert start == datetime(2026, 6, 6, 4, 0, tzinfo=timezone.utc)
