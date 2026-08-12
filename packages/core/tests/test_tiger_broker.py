"""Tiger broker option encoding and combo-type inference."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sigtrades_core.brokers.tiger.adapter import TigerBrokerAdapter
from sigtrades_core.signal.option_symbol import (
    ParsedOption,
    format_option_for_broker,
    format_tiger_option_identifier,
)


def test_tiger_apply_license_and_token_tbhk_requires_token():
    adapter = TigerBrokerAdapter(
        {"license": "tbhk", "token": "abc", "tiger_id": "1", "account": "1"}
    )
    assert adapter.license == "TBHK"
    cfg = SimpleNamespace(license=None, token=None)
    adapter._apply_license_and_token(cfg)
    assert cfg.license == "TBHK"
    assert cfg.token == "abc"

    missing = TigerBrokerAdapter({"license": "TBHK", "tiger_id": "1", "account": "1"})
    with pytest.raises(ValueError, match="TBHK"):
        missing._apply_license_and_token(SimpleNamespace(license=None, token=None))


def test_tiger_apply_license_and_token_tbnz_optional():
    adapter = TigerBrokerAdapter({"license": "TBNZ", "tiger_id": "1", "account": "1"})
    cfg = SimpleNamespace(license=None, token=None)
    adapter._apply_license_and_token(cfg)
    assert cfg.license == "TBNZ"
    assert getattr(cfg, "token", None) in (None, "")


def test_tiger_option_identifier_is_21_char_occ():
    parsed = ParsedOption(
        underlying="SPY",
        strike=680.0,
        right="P",
        put_call="PUT",
        expiry="2026-07-24",
        expiry_contract="20260724",
    )
    ident = format_tiger_option_identifier(parsed)
    assert ident == "SPY   260724P00680000"
    assert len(ident) == 21
    assert format_option_for_broker("tiger", parsed) == ident
    assert format_option_for_broker("alpaca", parsed) == "SPY260724P00680000"


def test_tiger_resolve_option_info_attaches_identifier():
    adapter = TigerBrokerAdapter({"env": "test", "tiger_id": "1", "account": "1"})
    info = adapter._resolve_option_info(
        "SPY260724P00680000",
        metadata={"underlying": "SPY"},
    )
    assert info["underlying"] == "SPY"
    assert info["strike"] == 680.0
    assert info["put_call"] == "PUT"
    assert info["identifier"] == "SPY   260724P00680000"


def test_tiger_infer_combo_type_vertical(monkeypatch):
    fake = SimpleNamespace(
        VERTICAL="VERTICAL",
        CALENDAR="CALENDAR",
        STRADDLE="STRADDLE",
        STRANGLE="STRANGLE",
        CUSTOM="CUSTOM",
    )
    monkeypatch.setattr(
        "sigtrades_core.brokers.tiger.adapter.ComboType",
        fake,
    )
    infos = [
        {
            "underlying": "SPY",
            "expiry_contract": "20260724",
            "strike": 680.0,
            "put_call": "PUT",
        },
        {
            "underlying": "SPY",
            "expiry_contract": "20260724",
            "strike": 679.0,
            "put_call": "PUT",
        },
    ]
    assert TigerBrokerAdapter._infer_combo_type(infos) == "VERTICAL"


def test_place_stock_order_uses_stock_contract_not_combo(monkeypatch):
    """正股必须走 stock_contract + market/limit_order；combo+STK 会被老虎报合约不正确。"""
    calls: dict = {}

    def fake_stock_contract(symbol, currency, **kwargs):
        calls["contract"] = (symbol, currency)
        return SimpleNamespace(symbol=symbol, currency=currency)

    def fake_market_order(**kwargs):
        calls["market"] = kwargs
        return SimpleNamespace(id="stk-1")

    def fake_limit_order(**kwargs):
        calls["limit"] = kwargs
        return SimpleNamespace(id="stk-2")

    monkeypatch.setattr(
        "sigtrades_core.brokers.tiger.adapter.stock_contract",
        fake_stock_contract,
    )
    monkeypatch.setattr(
        "sigtrades_core.brokers.tiger.adapter.market_order",
        fake_market_order,
    )
    monkeypatch.setattr(
        "sigtrades_core.brokers.tiger.adapter.limit_order",
        fake_limit_order,
    )
    monkeypatch.setattr(
        "sigtrades_core.brokers.tiger.adapter.combo_order",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("stock must not use combo_order")),
    )

    adapter = TigerBrokerAdapter({"env": "test", "tiger_id": "1", "account": "acc-1"})
    adapter.connected = True
    adapter.account = "acc-1"
    adapter.client_config = SimpleNamespace(account="acc-1")
    adapter.trade_client = SimpleNamespace(place_order=lambda order: calls.setdefault("placed", order))

    from sigtrades_core.signal.models import Signal

    signal = Signal.from_dict(
        {
            "signal_id": "t-stk",
            "timestamp": 1.0,
            "action": "BUY",
            "symbol": "TQQQ",
            "quantity": 10,
            "order_type": "MKT",
            "asset_class": "STOCK",
        }
    )
    result = adapter._place_stock_order(signal)
    assert result["status"] == "SUCCESS"
    assert result["order_id"] == "stk-1"
    assert calls["contract"] == ("TQQQ", "USD")
    assert calls["market"]["action"] == "BUY"
    assert calls["market"]["quantity"] == 10
    assert "limit" not in calls


def test_tiger_infer_combo_type_straddle(monkeypatch):
    fake = SimpleNamespace(
        VERTICAL="VERTICAL",
        CALENDAR="CALENDAR",
        STRADDLE="STRADDLE",
        STRANGLE="STRANGLE",
        CUSTOM="CUSTOM",
    )
    monkeypatch.setattr(
        "sigtrades_core.brokers.tiger.adapter.ComboType",
        fake,
    )
    infos = [
        {
            "underlying": "SPY",
            "expiry_contract": "20260724",
            "strike": 680.0,
            "put_call": "PUT",
        },
        {
            "underlying": "SPY",
            "expiry_contract": "20260724",
            "strike": 680.0,
            "put_call": "CALL",
        },
    ]
    assert TigerBrokerAdapter._infer_combo_type(infos) == "STRADDLE"


@pytest.mark.parametrize(
    "broker,expected",
    [
        ("futu", "US.SPY260724P680000"),
        ("longbridge", "SPY260724P680000.US"),
        ("schwab", "SPY   260724P00680000"),
    ],
)
def test_format_option_for_broker_matrix(broker: str, expected: str):
    parsed = ParsedOption(
        underlying="SPY",
        strike=680.0,
        right="P",
        put_call="PUT",
        expiry="2026-07-24",
        expiry_contract="20260724",
    )
    assert format_option_for_broker(broker, parsed) == expected
