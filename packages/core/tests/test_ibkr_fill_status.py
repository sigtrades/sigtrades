"""IBKR 轮询：Cancelled + fills 必须判成交，避免连环重下。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sigtrades_core.brokers.ibkr.adapter import IBKRBrokerAdapter
from sigtrades_core.execution.core import ExecutionCore
from sigtrades_core.signal.models import ExecutionConfig, Signal
from sigtrades_core.trading.order_status import OrderStatus


def _trade(*, status: str, status_filled: float = 0, qty: float = 1, fills_shares: float = 0):
    fills = []
    if fills_shares > 0:
        fills.append(
            SimpleNamespace(
                execution=SimpleNamespace(shares=fills_shares, avgPrice=1.25),
                commissionReport=SimpleNamespace(commission=0.1),
            )
        )
    return SimpleNamespace(
        order=SimpleNamespace(
            orderId=18,
            permId=99,
            totalQuantity=qty,
            orderType="LMT",
            lmtPrice=1.0,
            action="BUY",
        ),
        orderStatus=SimpleNamespace(
            status=status,
            filled=status_filled,
            remaining=max(0, qty - status_filled),
            avgFillPrice=1.25 if status_filled or fills_shares else 0,
        ),
        fills=fills,
    )


def test_format_order_prefers_fills_over_cancelled_status():
    adapter = IBKRBrokerAdapter({"host": "127.0.0.1", "port": 7497})
    info = adapter._format_order(_trade(status="Cancelled", status_filled=0, fills_shares=1))
    assert info["status"] == "Filled"
    assert info["std_status"] == OrderStatus.FILLED.value
    assert info["filled"] == 1


def test_execution_does_not_replace_after_spurious_cancel_with_fill():
    adapter = MagicMock()
    adapter.supports_combined_order.return_value = True
    adapter.place_order.return_value = {"order_id": "18", "status": "SUCCESS"}
    # 第一次轮询报 Cancelled 无成交；复核时带上成交
    adapter.get_order.side_effect = [
        {"order_id": "18", "status": "Cancelled", "std_status": "CANCELLED", "filled": 0},
        {"order_id": "18", "status": "Cancelled", "std_status": "CANCELLED", "filled": 1, "avg_fill_price": 1.2},
    ]

    t = {"n": 0.0}

    def now():
        return t["n"]

    def sleep(s):
        t["n"] += float(s)

    core = ExecutionCore(
        adapter=adapter,
        broker="ibkr",
        source_id="wh-1",
        sleep_fn=sleep,
        now_fn=now,
    )
    core.poll_interval = 0.1
    signal = Signal(
        signal_id="s1",
        timestamp=1.0,
        action="BUY",
        symbol="SPY",
        quantity=1,
        order_type="MKT",
        execution_config=ExecutionConfig(max_retry_attempts=5, limit_order_attempts=0, order_wait_timeout=2),
    )
    rpt = core.execute(signal, order_type_policy="MKT_only")
    assert rpt.status == "FILLED"
    assert adapter.place_order.call_count == 1
