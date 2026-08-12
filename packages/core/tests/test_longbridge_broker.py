"""长桥券商适配器工厂与状态映射测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from sigtrades_core.brokers import create_broker_adapter, deployment_for
from sigtrades_core.brokers.longbridge.adapter import LongbridgeBrokerAdapter
from sigtrades_core.brokers.status_mapping import LongbridgeStatusMapper, get_status_mapper
from sigtrades_core.signal.option_symbol import ParsedOption
from sigtrades_core.trading.order_status import OrderStatus


def test_create_longbridge_adapter():
    adapter = create_broker_adapter("longbridge", {
        "app_key": "k",
        "app_secret": "s",
        "access_token": "t",
        "env": "sandbox",
    })
    assert isinstance(adapter, LongbridgeBrokerAdapter)
    assert adapter.env == "sandbox"


def test_longbridge_deployment_is_cloud():
    assert deployment_for("longbridge") == "cloud"


def test_longbridge_status_mapper():
    mapper = get_status_mapper("longbridge")
    assert isinstance(mapper, LongbridgeStatusMapper)
    assert LongbridgeStatusMapper.to_standard("Filled") == OrderStatus.FILLED
    assert LongbridgeStatusMapper.to_standard("FilledStatus") == OrderStatus.FILLED
    assert LongbridgeStatusMapper.to_standard("NewStatus") == OrderStatus.NEW
    assert LongbridgeStatusMapper.to_standard("PartialFilledStatus") == OrderStatus.PARTIALLY_FILLED
    assert LongbridgeStatusMapper.to_standard("RejectedStatus") == OrderStatus.REJECTED
    assert LongbridgeStatusMapper.to_standard("CanceledStatus") == OrderStatus.CANCELLED
    assert LongbridgeStatusMapper.to_standard("Canceled") == OrderStatus.CANCELLED
    assert LongbridgeStatusMapper.to_standard("Rejected") == OrderStatus.REJECTED


def test_longbridge_get_order_uses_order_detail():
    adapter = LongbridgeBrokerAdapter({
        "app_key": "k",
        "app_secret": "s",
        "access_token": "t",
        "env": "live",
    })
    row = MagicMock()
    row.order_id = "1251579844169310208"
    row.status = "FilledStatus"
    row.symbol = "COST.US"
    row.quantity = "1"
    row.executed_quantity = "1"
    row.executed_price = "100.5"
    row.last_done = "100.5"
    row.side = "Buy"
    row.price = "100.0"
    adapter.trade_ctx = MagicMock()
    adapter.trade_ctx.order_detail.return_value = row

    result = adapter.get_order("1251579844169310208")
    assert result is not None
    assert result["status"] == "FILLED"
    assert result["fill_price"] == 100.5
    adapter.trade_ctx.order_detail.assert_called_once_with("1251579844169310208")


def test_longbridge_resolve_option_prefers_chain_symbol():
    adapter = LongbridgeBrokerAdapter({
        "app_key": "k",
        "app_secret": "s",
        "access_token": "t",
        "env": "live",
    })
    row = MagicMock()
    row.price = "27.5"
    row.call_symbol = "CIFR260618C27500.US"
    row.put_symbol = "CIFR260618P27500.US"
    adapter.quote_ctx = MagicMock()
    adapter.quote_ctx.option_chain_info_by_date.return_value = [row]
    adapter._lb_config = MagicMock()

    parsed = ParsedOption(
        underlying="CIFR",
        strike=27.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-18",
        expiry_contract="20260618",
    )
    assert adapter._resolve_lb_option_symbol(parsed) == "CIFR260618C27500.US"
    adapter.quote_ctx.option_chain_info_by_date.assert_called_once_with("CIFR.US", "20260618")


def test_longbridge_resolve_option_falls_back_to_local_format():
    adapter = LongbridgeBrokerAdapter({
        "app_key": "k",
        "app_secret": "s",
        "access_token": "t",
        "env": "live",
    })
    adapter.quote_ctx = MagicMock()
    adapter.quote_ctx.option_chain_info_by_date.return_value = []
    adapter._lb_config = MagicMock()

    parsed = ParsedOption(
        underlying="CIFR",
        strike=27.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-18",
        expiry_contract="20260618",
    )
    assert adapter._resolve_lb_option_symbol(parsed) == "CIFR260618C27500.US"


def test_longbridge_sandbox_skips_option_chain():
    adapter = LongbridgeBrokerAdapter({
        "app_key": "k",
        "app_secret": "s",
        "access_token": "t",
        "env": "sandbox",
    })
    adapter._lookup_option_symbol_from_chain = MagicMock(return_value="SHOULD_NOT_USE")

    parsed = ParsedOption(
        underlying="CIFR",
        strike=27.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-18",
        expiry_contract="20260618",
    )
    assert adapter._resolve_lb_option_symbol(parsed) == "CIFR260618C27500.US"
    adapter._lookup_option_symbol_from_chain.assert_not_called()


def test_longbridge_connect_requires_credentials():
    adapter = LongbridgeBrokerAdapter({"env": "sandbox"})
    assert adapter.connect() is False
    assert adapter.connect_error
    assert "凭证不完整" in adapter.connect_error


def test_longbridge_rejects_multi_leg_without_placing():
    from sigtrades_core.signal.models import OptionLeg, Signal

    adapter = LongbridgeBrokerAdapter({
        "app_key": "k",
        "app_secret": "s",
        "access_token": "t",
        "env": "sandbox",
    })
    adapter.trade_ctx = MagicMock()
    signal = Signal(
        signal_id="pcs-1",
        timestamp=1.0,
        action="组合",
        symbol="SPY",
        quantity=1,
        legs=[
            OptionLeg(symbol="SPY260724P00600000", action="SELL", quantity=1),
            OptionLeg(symbol="SPY260724P00599000", action="BUY", quantity=1),
        ],
    )
    result = adapter.place_order(signal)
    assert result["status"] == "FAILED"
    assert result.get("retryable") is False
    assert "多腿" in (result.get("error") or "")
    adapter.trade_ctx.submit_order.assert_not_called()
