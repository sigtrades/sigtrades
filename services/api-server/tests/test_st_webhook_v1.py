"""st_webhook_v1 ingest tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_webhook():
    root = Path(__file__).resolve().parents[2]
    path = root / "ingest" / "app" / "connectors" / "webhook.py"
    spec = importlib.util.spec_from_file_location("webhook_connector", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # sunnyquant is imported by webhook; load package path
    ingest_root = root / "ingest"
    import sys

    if str(ingest_root) not in sys.path:
        sys.path.insert(0, str(ingest_root))
    spec.loader.exec_module(mod)
    return mod


def test_st_webhook_v1_stock_passthrough():
    mod = _load_webhook()
    payload = {
        "contract_version": "st_webhook_v1",
        "signal_id": "st-test-001",
        "action": "BUY",
        "symbol": "AAPL",
        "quantity": 10,
        "order_type": "MKT",
        "asset_class": "STOCK",
    }
    signal_id, inbound = mod.parse_webhook_payload(payload, "wh-test", "user-1")
    assert signal_id == "st-test-001"
    sig = inbound["signal"]
    assert sig["symbol"] == "AAPL"
    assert sig["action"] == "BUY"
    assert sig["asset_class"] == "STOCK"
    assert "contract_version" not in sig
    assert sig["metadata"]["contract_version"] == "st_webhook_v1"
    assert inbound["owner_user_id"] == "user-1"


def test_st_webhook_v1_options_legs():
    mod = _load_webhook()
    payload = {
        "contract_version": "st_webhook_v1",
        "signal_id": "st-opt-1",
        "action": "组合",
        "symbol": "SPX",
        "quantity": 1,
        "order_type": "MKT",
        "asset_class": "OPTIONS",
        "legs": [
            {
                "symbol": "SPX 240119P04500000",
                "action": "SELL",
                "quantity": 1,
                "strike": 4500,
                "option_type": "PUT",
            }
        ],
        "metadata": {"underlying": "SPX", "expiry": "2024-01-19"},
    }
    signal_id, inbound = mod.parse_webhook_payload(payload, "wh-test", None)
    assert signal_id == "st-opt-1"
    assert inbound["signal"]["legs"][0]["strike"] == 4500
