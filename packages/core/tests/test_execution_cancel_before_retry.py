"""LMT 超时后必须先撤单再下 MKT，避免双挂。"""

from __future__ import annotations

from unittest.mock import MagicMock

from sigtrades_core.execution.core import ExecutionCore
from sigtrades_core.signal.models import ExecutionConfig, Signal


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += float(s)


def test_expired_limit_order_is_cancelled_before_market_retry():
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = True
    adapter.place_order.side_effect = [
        {"order_id": "lmt-1", "status": "SUCCESS"},
        {"order_id": "mkt-2", "status": "SUCCESS"},
    ]

    def get_order(oid):
        if adapter.place_order.call_count >= 2 or str(oid) == "mkt-2":
            return {"order_id": "mkt-2", "status": "FILLED", "filled": 1, "avg_fill_price": 1.1}
        if adapter.cancel_order.call_count >= 1:
            return {
                "order_id": "lmt-1",
                "status": "CANCELLED",
                "std_status": "CANCELLED",
                "filled": 0,
            }
        return {"order_id": "lmt-1", "status": "PENDING", "filled": 0}

    adapter.get_order.side_effect = get_order
    adapter.cancel_order.return_value = True

    clock = _Clock()
    core = ExecutionCore(
        adapter=adapter,
        broker="tiger",
        source_id="wh-1",
        sleep_fn=clock.sleep,
        now_fn=clock.now,
    )
    core.poll_interval = 0.5
    signal = Signal(
        signal_id="s-expire-retry",
        timestamp=1.0,
        action="BUY",
        symbol="SPY",
        quantity=1,
        limit_price=1.5,
        order_type="LMT",
        execution_config=ExecutionConfig(
            max_retry_attempts=2,
            limit_order_attempts=1,
            order_wait_timeout=1,
        ),
    )
    rpt = core.execute(signal, order_type_policy="LMT_then_MKT")

    assert rpt.status == "FILLED"
    assert rpt.order_id == "mkt-2"
    assert adapter.place_order.call_count == 2
    adapter.cancel_order.assert_called_once_with("lmt-1")
    names = [c[0] for c in adapter.method_calls if c[0] in ("place_order", "cancel_order")]
    assert names == ["place_order", "cancel_order", "place_order"]


def test_cancelled_order_still_cancelled_idempotently_before_retry():
    """误报/真撤都再撤一次（幂等），确认清掉后才下 MKT。"""
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = True
    adapter.place_order.side_effect = [
        {"order_id": "o1", "status": "SUCCESS"},
        {"order_id": "o2", "status": "SUCCESS"},
    ]

    def get_order(oid):
        if str(oid) == "o2" or adapter.place_order.call_count >= 2:
            return {"order_id": "o2", "status": "FILLED", "filled": 1, "avg_fill_price": 1.0}
        return {
            "order_id": "o1",
            "status": "CANCELLED",
            "std_status": "CANCELLED",
            "filled": 0,
        }

    adapter.get_order.side_effect = get_order
    adapter.cancel_order.return_value = True

    clock = _Clock()
    core = ExecutionCore(
        adapter=adapter,
        broker="tiger",
        source_id="wh-1",
        sleep_fn=clock.sleep,
        now_fn=clock.now,
    )
    core.poll_interval = 0.1
    signal = Signal(
        signal_id="s-already-cancelled",
        timestamp=1.0,
        action="BUY",
        symbol="SPY",
        quantity=1,
        limit_price=1.5,
        order_type="LMT",
        execution_config=ExecutionConfig(
            max_retry_attempts=2,
            limit_order_attempts=1,
            order_wait_timeout=2,
        ),
    )
    rpt = core.execute(signal, order_type_policy="LMT_then_MKT")
    assert rpt.status == "FILLED"
    assert adapter.place_order.call_count == 2
    adapter.cancel_order.assert_called_once_with("o1")


def test_still_live_after_failed_cancel_blocks_market_retry():
    """撤单失败且订单仍挂着时，禁止再下市价。"""
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = True
    adapter.place_order.return_value = {"order_id": "lmt-1", "status": "SUCCESS"}
    adapter.get_order.return_value = {
        "order_id": "lmt-1",
        "status": "PENDING",
        "filled": 0,
    }
    adapter.cancel_order.return_value = False

    clock = _Clock()
    core = ExecutionCore(
        adapter=adapter,
        broker="tiger",
        source_id="wh-1",
        sleep_fn=clock.sleep,
        now_fn=clock.now,
    )
    core.poll_interval = 0.5
    signal = Signal(
        signal_id="s-block-double",
        timestamp=1.0,
        action="BUY",
        symbol="SPY",
        quantity=1,
        limit_price=1.5,
        order_type="LMT",
        execution_config=ExecutionConfig(
            max_retry_attempts=3,
            limit_order_attempts=1,
            order_wait_timeout=1,
        ),
    )
    rpt = core.execute(signal, order_type_policy="LMT_then_MKT")
    assert adapter.place_order.call_count == 1
    assert "重复下单" in (rpt.error or "")


def test_tiger_standard_status_field_is_honored():
    """Tiger 适配器返回 standard_status，须能正确识别已撤。"""
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = True
    adapter.place_order.side_effect = [
        {"order_id": "t1", "status": "SUCCESS"},
        {"order_id": "t2", "status": "SUCCESS"},
    ]

    def get_order(oid):
        if str(oid) == "t2" or adapter.place_order.call_count >= 2:
            return {
                "order_id": "t2",
                "status": "已成交",
                "standard_status": "FILLED",
                "filled": 1,
                "avg_fill_price": 0.9,
            }
        if adapter.cancel_order.call_count >= 1:
            return {
                "order_id": "t1",
                "status": "已取消",
                "standard_status": "CANCELLED",
                "filled": 0,
            }
        return {
            "order_id": "t1",
            "status": "已提交",
            "standard_status": "SUBMITTED",
            "filled": 0,
        }

    adapter.get_order.side_effect = get_order
    adapter.cancel_order.return_value = True

    clock = _Clock()
    core = ExecutionCore(
        adapter=adapter,
        broker="tiger",
        source_id="wh-1",
        sleep_fn=clock.sleep,
        now_fn=clock.now,
    )
    core.poll_interval = 0.5
    signal = Signal(
        signal_id="s-tiger-std",
        timestamp=1.0,
        action="BUY",
        symbol="SPY",
        quantity=1,
        limit_price=1.5,
        order_type="LMT",
        execution_config=ExecutionConfig(
            max_retry_attempts=2,
            limit_order_attempts=1,
            order_wait_timeout=1,
        ),
    )
    rpt = core.execute(signal, order_type_policy="LMT_then_MKT")
    assert rpt.status == "FILLED"
    assert adapter.place_order.call_count == 2
    adapter.cancel_order.assert_called_once_with("t1")
