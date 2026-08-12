"""SunnyQuant sq_webhook_v2 ingest tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sunnyquant():
    root = Path(__file__).resolve().parents[2]
    path = root / "ingest" / "app" / "connectors" / "sunnyquant.py"
    spec = importlib.util.spec_from_file_location("sunnyquant_connector", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _v2_content_payload() -> dict:
    """与 sunny-quant front/apiPushWebhookExample.ts 一致的内容型 v2。"""
    return {
        "contract_version": "sq_webhook_v2",
        "event": "structure_signal",
        "signal_id": "GEX_20260619_093100_pcs_basic",
        "timestamp": 1739811660,
        "strategy": "SQ-TGT",
        "strategy_family": "vertical_spread",
        "audience": "pcs_basic",
        "signal_subtype": "ENTRY",
        "asset_class": "SPX_OPTIONS",
        "direction": "down",
        "spx_price": 6123.45,
        "title": "PCS 信号观察开始 · PCS 结构 · 下方参考位 · 6,050 · 0·DTE",
        "content": "**PCS 信号观察开始 · PCS 结构 · 下方参考位**\n\nSPX **6123.45**",
        "disclaimer": "本提醒由系统根据 GEX 结构数据自动生成…（风险说明）",
        "structure": {
            "exit_reason": None,
            "parent_signal_id": None,
            "spx_price": 6123.45,
            "reference_width": 20,
            "references": [
                {"option_type": "P", "inner": 6050, "outer": 6030},
            ],
        },
        "delivery": {
            "tier": "external",
            "delay_sec": 0,
            "deliver_after_ts": 1739811660,
        },
        "subscriber": {"user_id": "00000000-0000-0000-0000-000000000001"},
        "source": "sunnyquant.gex_structure_reminder",
    }


def test_v2_content_maps_to_alert_signal():
    mod = _load_sunnyquant()
    signal_id, inbound = mod.parse_sunnyquant_webhook(_v2_content_payload(), "wh-test", "user-1")
    assert signal_id == "GEX_20260619_093100_pcs_basic"
    sig = inbound["signal"]
    assert sig["signal_category"] == "ALERT"
    assert sig["signal_subtype"] == "OPEN"
    assert sig["auto_trade_enabled"] is False
    assert sig["quantity"] == 0
    assert sig["legs"] is None
    assert sig["action"] == ""
    assert sig["strategy"] == "SQ-TGT"
    sq = sig["metadata"]["sunnyquant"]
    assert sq["content_only"] is True
    assert sq["event"] == "structure_signal"
    assert sq["title"].startswith("PCS 信号观察开始")
    assert sq["structure"]["references"][0]["inner"] == 6050
    assert inbound["owner_user_id"] == "user-1"


def test_v2_exit_maps_close_subtype():
    mod = _load_sunnyquant()
    payload = _v2_content_payload()
    payload["signal_id"] = "GEX_20260619_110000_pcs_basic_exit"
    payload["signal_subtype"] = "EXIT"
    payload["structure"]["exit_reason"] = "structure_invalidation"
    payload["structure"]["parent_signal_id"] = "GEX_20260619_093100_pcs_basic"
    signal_id, inbound = mod.parse_sunnyquant_webhook(payload, "wh-test", "user-1")
    assert signal_id.endswith("_exit")
    assert inbound["signal"]["signal_subtype"] == "CLOSE"


def test_v2_legacy_order_still_ingests():
    mod = _load_sunnyquant()
    payload = {
        "contract_version": "sq_webhook_v2",
        "signal_id": "GEX_TEST",
        "timestamp": 1700000000,
        "strategy": "SQ-TGT",
        "signal_subtype": "ENTRY",
        "signal_subtype_trade": "OPEN",
        "asset_class": "SPX_OPTIONS",
        "order": {
            "action": "组合",
            "symbol": "SPX",
            "quantity": 1,
            "order_type": "LMT",
            "limit_price": 0.85,
            "legs": [{"symbol": "A", "action": "SELL", "quantity": 1}],
        },
        "execution": {"leg_width": 20},
        "source": "sunnyquant.gex_structure_reminder",
    }
    signal_id, inbound = mod.parse_sunnyquant_webhook(payload, "wh-test", "user-1")
    assert signal_id == "GEX_TEST"
    sig = inbound["signal"]
    assert sig["signal_category"] == "TRADE"
    assert sig["action"] == "组合"
    assert sig["signal_subtype"] == "OPEN"
    assert sig["legs"][0]["symbol"] == "A"
    assert sig["metadata"]["sunnyquant"]["content_only"] is False


def test_v2_order_legs_normalized():
    """order.legs 含未知键/缺 quantity 时清洗为 OptionLeg 可接受的字段。"""
    mod = _load_sunnyquant()
    payload = {
        "contract_version": "sq_webhook_v2",
        "signal_id": "GEX_LEGS",
        "signal_subtype_trade": "OPEN",
        "order": {
            "action": "组合",
            "symbol": "SPX",
            "quantity": 1,
            "order_type": "LMT",
            "legs": [
                {"symbol": "SPXW250619P06050000", "action": "SELL", "strike": 6050, "bid": 1.2, "ask": 1.4},
                {"symbol": "SPXW250619P06030000", "action": "BUY", "strike": 6030, "option_type": "PUT"},
            ],
        },
        "source": "sunnyquant.gex_structure_reminder",
    }
    _, inbound = mod.parse_sunnyquant_webhook(payload, "wh-test", "user-1")
    legs = inbound["signal"]["legs"]
    assert len(legs) == 2
    assert legs[0] == {"symbol": "SPXW250619P06050000", "action": "SELL", "strike": 6050, "quantity": 1}
    assert "bid" not in legs[0] and "ask" not in legs[0]
    assert legs[1]["quantity"] == 1
    assert legs[1]["option_type"] == "PUT"


def test_v1_legacy_still_ingests():
    mod = _load_sunnyquant()
    payload = {
        "contract_version": "sq_webhook_v1",
        "signal_id": "LEGACY",
        "strategy": "gex_pin",
        "strategy_code": "gex_pin",
        "signal_subtype": "ENTRY",
        "metadata": {"premium_snapshot": {"base": {"strike": 6000}}},
        "source": "sunnyquant.gex_structure_reminder",
    }
    signal_id, inbound = mod.parse_sunnyquant_webhook(payload, "wh-test", None)
    assert signal_id == "LEGACY"
    assert inbound["signal"]["signal_subtype"] == "OPEN"
    assert inbound["signal"]["metadata"]["sunnyquant"]["legacy_v1"] is True
