"""Charles Schwab broker factory, payload, and status tests."""

from __future__ import annotations

import time

import httpx

from sigtrades_core.brokers import create_broker_adapter, deployment_for
from sigtrades_core.brokers.schwab.adapter import SchwabBrokerAdapter
from sigtrades_core.brokers.status_mapping import SchwabStatusMapper, get_status_mapper
from sigtrades_core.signal.models import Signal
from sigtrades_core.signal.option_symbol import ParsedOption, format_schwab_option_symbol
from sigtrades_core.trading.order_status import OrderStatus


def _config() -> dict:
    return {
        "client_id": "app-key",
        "client_secret": "app-secret",
        "refresh_token": "refresh-token",
        "account_hash": "HASH123",
        "account_number": "1234",
    }


def test_create_schwab_adapter_and_cloud_deployment():
    adapter = create_broker_adapter("schwab", _config())
    assert isinstance(adapter, SchwabBrokerAdapter)
    assert deployment_for("schwab") == "cloud"


def test_schwab_status_mapper():
    mapper = get_status_mapper("schwab")
    assert isinstance(mapper, SchwabStatusMapper)
    assert mapper.to_standard("WORKING") == OrderStatus.SUBMITTED
    assert mapper.to_standard("FILLED") == OrderStatus.FILLED
    assert mapper.to_standard("CANCELED") == OrderStatus.CANCELLED
    assert mapper.to_standard("REJECTED") == OrderStatus.REJECTED


def test_schwab_option_symbol_is_occ_padded():
    parsed = ParsedOption(
        underlying="AAPL",
        strike=297.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-26",
        expiry_contract="20260626",
    )
    assert format_schwab_option_symbol(parsed) == "AAPL  260626C00297500"


def test_schwab_builds_single_leg_option_limit_order():
    adapter = SchwabBrokerAdapter(_config())
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
    leg = payload["orderLegCollection"][0]
    assert payload["orderType"] == "LIMIT"
    assert payload["price"] == "1.25"
    assert leg["instruction"] == "BUY_TO_OPEN"
    assert leg["instrument"] == {
        "symbol": "AAPL  260626C00297500",
        "assetType": "OPTION",
    }


def test_schwab_connect_and_place_stock_order():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={"access_token": "access"})
        if request.method == "GET" and request.url.path.endswith("/accounts/HASH123"):
            return httpx.Response(200, json={"securitiesAccount": {}})
        if request.method == "POST" and request.url.path.endswith("/accounts/HASH123/orders"):
            return httpx.Response(
                201,
                headers={"Location": "https://api.schwabapi.com/trader/v1/accounts/HASH123/orders/987"},
            )
        return httpx.Response(404)

    adapter = SchwabBrokerAdapter(_config())
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
    assert result == {"order_id": "987", "status": "SUCCESS", "error": None}
    assert len(calls) == 3


def test_schwab_normalizes_fill_price():
    row = {
        "orderId": 987,
        "status": "FILLED",
        "quantity": 2,
        "filledQuantity": 2,
        "orderLegCollection": [
            {
                "instruction": "BUY_TO_OPEN",
                "quantity": 2,
                "instrument": {"symbol": "AAPL  260626C00297500", "assetType": "OPTION"},
            }
        ],
        "orderActivityCollection": [
            {
                "executionLegs": [
                    {"quantity": 1, "price": 1.2},
                    {"quantity": 1, "price": 1.4},
                ]
            }
        ],
    }
    result = SchwabBrokerAdapter._normalize_order(row)
    assert result["status"] == "FILLED"
    assert result["fill_price"] == 1.3
