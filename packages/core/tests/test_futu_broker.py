# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from sigtrades_core.brokers.futu import adapter as futu_mod
from sigtrades_core.brokers.futu.adapter import FutuBrokerAdapter
from sigtrades_core.signal.models import OptionLeg, Signal


def _pcs_signal() -> Signal:
    return Signal(
        signal_id="pcs-futu-1",
        timestamp=1.0,
        action="组合",
        symbol="SPX",
        quantity=1,
        order_type="LMT",
        limit_price=0.3,
        asset_class="SPX_OPTIONS",
        legs=[
            OptionLeg(
                symbol="SPXW260729P07370000",
                action="SELL",
                quantity=1,
                option_type="PUT",
                strike=7370,
            ),
            OptionLeg(
                symbol="SPXW260729P07365000",
                action="BUY",
                quantity=1,
                option_type="PUT",
                strike=7365,
            ),
        ],
    )


def test_futu_supports_combined_order():
    assert FutuBrokerAdapter.supports_combined_order(FutuBrokerAdapter.__new__(FutuBrokerAdapter)) is True


def test_opend_version_warning_for_legacy():
    assert futu_mod.opend_combo_version_warning(906)
    assert "9.06" in (futu_mod.opend_combo_version_warning(906) or "")
    assert futu_mod.opend_combo_version_warning(1009) is None
    assert futu_mod.format_opend_server_ver(906) == "9.06"


def test_futu_place_combo_uses_native_api(monkeypatch):
    class FakeComboLeg:
        def __init__(self):
            self.code = None
            self.trd_side = None
            self.qty_ratio = None

    monkeypatch.setattr(futu_mod, "ComboLeg", FakeComboLeg)
    monkeypatch.setattr(futu_mod, "TimeInForce", SimpleNamespace(DAY="DAY"))
    monkeypatch.setattr(futu_mod, "OrderType", SimpleNamespace(NORMAL="NORMAL", MARKET="MARKET"))
    monkeypatch.setattr(futu_mod, "TrdSide", SimpleNamespace(BUY="BUY", SELL="SELL"))
    monkeypatch.setattr(futu_mod, "RET_OK", 0)

    adapter = FutuBrokerAdapter.__new__(FutuBrokerAdapter)
    adapter.connected = True
    # 模拟盘不支持组合期权；单测走 REAL 路径验证代码与 API 调用
    adapter.trd_env = SimpleNamespace(name="REAL")
    adapter.trd_ctx = MagicMock()
    adapter.trd_ctx.place_combo_order.return_value = (
        0,
        pd.DataFrame([{"order_id": "FH_COMBO_1"}]),
    )

    result = adapter.place_order(_pcs_signal())
    assert result["status"] == "SUCCESS"
    assert result["order_id"] == "FH_COMBO_1"
    adapter.trd_ctx.place_combo_order.assert_called_once()
    kwargs = adapter.trd_ctx.place_combo_order.call_args.kwargs
    assert kwargs["qty"] == 1.0
    assert kwargs["price"] == 0.3
    assert len(kwargs["combo_leg_list"]) == 2
    assert kwargs["combo_leg_list"][0].trd_side == "SELL"
    assert kwargs["combo_leg_list"][1].trd_side == "BUY"
    # 指数期权单点 US.SPXW…（勿用 US..）
    assert all(c.code.startswith("US.SPXW") for c in kwargs["combo_leg_list"])
    assert all(not c.code.startswith("US..") for c in kwargs["combo_leg_list"])


def test_futu_place_combo_rejects_simulate_env(monkeypatch):
    monkeypatch.setattr(futu_mod, "ComboLeg", object)
    monkeypatch.setattr(futu_mod, "TrdEnv", SimpleNamespace(SIMULATE="SIMULATE", REAL="REAL"))
    adapter = FutuBrokerAdapter.__new__(FutuBrokerAdapter)
    adapter.connected = True
    adapter.trd_env = "SIMULATE"
    adapter.trd_ctx = MagicMock()
    adapter.trd_ctx.place_combo_order = MagicMock()

    result = adapter._place_combo_order(_pcs_signal(), "LMT", 1)
    assert result["status"] == "FAILED"
    assert "模拟" in (result.get("error") or "")
    adapter.trd_ctx.place_combo_order.assert_not_called()


def test_futu_place_combo_requires_modern_sdk(monkeypatch):
    monkeypatch.setattr(futu_mod, "ComboLeg", None)
    adapter = FutuBrokerAdapter.__new__(FutuBrokerAdapter)
    adapter.connected = True
    adapter.trd_env = "SIMULATE"
    adapter.trd_ctx = MagicMock(spec=[])  # no place_combo_order

    result = adapter._place_combo_order(_pcs_signal(), "LMT", 1)
    assert result["status"] == "FAILED"
    assert "place_combo_order" in (result.get("error") or "")


def test_futu_place_combo_rewrites_unknown_protocol(monkeypatch):
    class FakeComboLeg:
        def __init__(self):
            self.code = None
            self.trd_side = None
            self.qty_ratio = None

    monkeypatch.setattr(futu_mod, "ComboLeg", FakeComboLeg)
    monkeypatch.setattr(futu_mod, "TimeInForce", SimpleNamespace(DAY="DAY"))
    monkeypatch.setattr(futu_mod, "OrderType", SimpleNamespace(NORMAL="NORMAL", MARKET="MARKET"))
    monkeypatch.setattr(futu_mod, "TrdSide", SimpleNamespace(BUY="BUY", SELL="SELL"))
    monkeypatch.setattr(futu_mod, "RET_OK", 0)

    adapter = FutuBrokerAdapter.__new__(FutuBrokerAdapter)
    adapter.connected = True
    adapter.trd_env = SimpleNamespace(name="REAL")
    adapter.opend_server_ver = 906
    adapter.opend_version_warning = futu_mod.opend_combo_version_warning(906)
    adapter.trd_ctx = MagicMock()
    adapter.trd_ctx.place_combo_order.return_value = (-1, "未知的协议ID")

    result = adapter._place_combo_order(_pcs_signal(), "LMT", 1)
    assert result["status"] == "FAILED"
    assert "OpenD" in (result.get("error") or "")
    assert "9.06" in (result.get("error") or "")
