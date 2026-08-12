"""不可重试下单失败应立即停止，不再 LMT→MKT 轮询重下。"""

from __future__ import annotations

from unittest.mock import MagicMock

from sigtrades_core.execution.core import ExecutionCore
from sigtrades_core.signal.models import OptionLeg, Signal


def test_execution_stops_when_broker_rejects_multi_leg():
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = False
    adapter.place_order.side_effect = AssertionError("should not place")

    core = ExecutionCore(
        adapter=adapter,
        broker="longbridge",
        source_id="wh-1",
        sleep_fn=lambda _s: None,
        now_fn=lambda: 0.0,
    )
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
    rpt = core.execute(signal, order_type_policy="LMT_then_MKT")
    assert rpt.status == "REJECTED"
    assert "多腿" in (rpt.error or "")
    assert rpt.attempt == 1
    adapter.place_order.assert_not_called()


def test_execution_stops_on_retryable_false():
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = True
    adapter.place_order.return_value = {
        "order_id": None,
        "status": "FAILED",
        "retryable": False,
        "error": "无法交易：合约无效",
    }

    core = ExecutionCore(
        adapter=adapter,
        broker="tiger",
        source_id="wh-1",
        sleep_fn=lambda _s: None,
        now_fn=lambda: 0.0,
    )
    signal = Signal(
        signal_id="s1",
        timestamp=1.0,
        action="BUY",
        symbol="AAPL",
        quantity=1,
    )
    rpt = core.execute(signal, order_type_policy="MKT_only")
    assert rpt.status == "REJECTED"
    assert rpt.attempt == 1
    assert adapter.place_order.call_count == 1
