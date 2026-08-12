"""Alpaca broker factory, payload, and status tests."""

from __future__ import annotations

import time

import httpx

from sigtrades_core.brokers import create_broker_adapter, deployment_for
from sigtrades_core.brokers.alpaca.adapter import AlpacaBrokerAdapter
from sigtrades_core.brokers.status_mapping import AlpacaStatusMapper, get_status_mapper
from sigtrades_core.signal.models import OptionLeg, Signal
from sigtrades_core.signal.option_symbol import ParsedOption, format_alpaca_option_symbol
from sigtrades_core.trading.order_status import OrderStatus


def _config() -> dict:
    return {"api_key": "key-id", "api_secret": "secret", "env": "paper"}


def test_create_alpaca_adapter_and_cloud_deployment():
    adapter = create_broker_adapter("alpaca", _config())
    assert isinstance(adapter, AlpacaBrokerAdapter)
    assert adapter.base_url == "https://paper-api.alpaca.markets"
    assert deployment_for("alpaca") == "cloud"


def test_alpaca_status_mapper():
    mapper = get_status_mapper("alpaca")
    assert isinstance(mapper, AlpacaStatusMapper)
    assert mapper.to_standard("accepted") == OrderStatus.SUBMITTED
    assert mapper.to_standard("partially_filled") == OrderStatus.PARTIALLY_FILLED
    assert mapper.to_standard("filled") == OrderStatus.FILLED
    assert mapper.to_standard("canceled") == OrderStatus.CANCELLED


def test_alpaca_option_symbol_is_compact_occ():
    parsed = ParsedOption(
        underlying="AAPL",
        strike=297.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-26",
        expiry_contract="20260626",
    )
    assert format_alpaca_option_symbol(parsed) == "AAPL260626C00297500"


def test_alpaca_builds_option_limit_order():
    adapter = AlpacaBrokerAdapter(_config())
    signal = Signal(
        signal_id="sig-1",
        timestamp=time.time(),
        action="BUY",
        symbol="AAPL 260626C297.5",
        quantity=2,
        order_type="LMT",
        limit_price=1.25,
        asset_class="STOCK_OPTIONS",
        metadata={
            "underlying": "AAPL",
            "strike": 297.5,
            "right": "C",
            "expiry": "2026-06-26",
        },
    )
    payload = adapter._order_payload(signal)
    assert payload == {
        "symbol": "AAPL260626C00297500",
        "qty": "2",
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "position_intent": "buy_to_open",
        "limit_price": "1.25",
    }


def test_alpaca_builds_mleg_put_credit_spread():
    adapter = AlpacaBrokerAdapter(_config())
    signal = Signal(
        signal_id="sig-mleg",
        timestamp=time.time(),
        action="组合",
        symbol="SPX",
        quantity=1,
        order_type="LMT",
        limit_price=0.85,
        asset_class="SPX_OPTIONS",
        signal_subtype="OPEN",
        legs=[
            OptionLeg(symbol="SPXW250721P07450000", action="SELL", quantity=1),
            OptionLeg(symbol="SPXW250721P07445000", action="BUY", quantity=1),
        ],
    )
    payload = adapter._order_payload(signal)
    assert payload["order_class"] == "mleg"
    assert payload["qty"] == "1"
    assert payload["type"] == "limit"
    assert payload["limit_price"] == "0.85"
    assert payload["legs"] == [
        {
            "symbol": "SPXW250721P07450000",
            "ratio_qty": "1",
            "side": "sell",
            "position_intent": "sell_to_open",
        },
        {
            "symbol": "SPXW250721P07445000",
            "ratio_qty": "1",
            "side": "buy",
            "position_intent": "buy_to_open",
        },
    ]
    assert adapter.supports_combined_order() is True


def test_alpaca_connect_and_place_stock_order():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET" and request.url.path == "/v2/account":
            return httpx.Response(200, json={"id": "account-1"})
        if request.method == "POST" and request.url.path == "/v2/orders":
            return httpx.Response(200, json={"id": "order-987"})
        return httpx.Response(404)

    adapter = AlpacaBrokerAdapter(_config())
    adapter._client.close()
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert adapter.connect() is True

    result = adapter.place_order(
        Signal(
            signal_id="sig-2",
            timestamp=time.time(),
            action="BUY",
            symbol="AAPL",
            quantity=1,
            order_type="MKT",
            asset_class="STOCK",
        )
    )
    assert result == {"order_id": "order-987", "status": "SUCCESS", "error": None}
    assert calls[-1].headers["APCA-API-KEY-ID"] == "key-id"


def test_alpaca_normalizes_fill():
    result = AlpacaBrokerAdapter._normalize_order({
        "id": "order-987",
        "status": "filled",
        "symbol": "AAPL",
        "qty": "2",
        "filled_qty": "2",
        "filled_avg_price": "212.35",
        "limit_price": None,
        "side": "buy",
    })
    assert result["status"] == "FILLED"
    assert result["fill_price"] == 212.35
