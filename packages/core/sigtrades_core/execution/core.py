"""执行状态机（去 Qt 版）。

从 sigx `fluent_main_window` 的执行链抽取并通用化：
  _execute_signal → _handle_order_result → 超时轮询 → _check_order_status_and_retry → _cancel_and_retry

设计：
- 与框架无关：不依赖 Qt / asyncio。`execute()` 同步阻塞直至终态，由调用方放在正确的线程中运行
  （IBKR 专属事件循环线程 / 富途 worker 线程 / cloud-executor 老虎线程）。
- 下单 / 订单查询 / 重试 / 撤单重下全在本机完成；通过 `on_report` 回调把有意义的状态变更上报。
- 幂等由上层（Agent/executor）按 (source_id, signal_id) 负责，core 只管单条信号的执行生命周期。
- 下单类型策略：LMT_then_MKT（默认）/ MKT_only（解析不出可靠价，对应 limit_order_attempts=0）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

from sigtrades_core.signal.models import Signal, ExecutionConfig
from sigtrades_core.signal.option_symbol import normalize_option_signal
from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.trading.order_status import (
    OrderStatus,
    get_status_from_string,
    is_terminal_status,
    is_success_status,
)

logger = logging.getLogger(__name__)

LMT_THEN_MKT = "LMT_then_MKT"
MKT_ONLY = "MKT_only"


@dataclass
class ExecutionReportData:
    """单次状态变更的回执（与 protocol.ExecutionReport 字段对齐）。"""
    signal_id: str
    source_id: str
    broker: str
    status: str
    account_id: Optional[str] = None
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    asset_type: Optional[str] = None
    quantity: Optional[float] = None
    limit_price: Optional[float] = None
    fill_price: Optional[float] = None
    filled_qty: Optional[float] = None
    amount: Optional[float] = None
    realized_pnl: Optional[float] = None
    attempt: int = 1
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


ReportCallback = Callable[[ExecutionReportData], None]


class ExecutionCore:
    """单券商执行核心。一个实例绑定一个已连接的 broker adapter。"""

    def __init__(
        self,
        adapter: BaseBrokerAdapter,
        broker: str,
        source_id: str = "",
        account_id: Optional[str] = None,
        on_report: Optional[ReportCallback] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        now_fn: Callable[[], float] = time.time,
        should_continue: Optional[Callable[[], bool]] = None,
    ):
        self.adapter = adapter
        self.broker = broker
        self.source_id = source_id
        self.account_id = account_id
        self.on_report = on_report
        self._sleep = sleep_fn
        self._now = now_fn
        # 全局急停钩子：返回 False 则中止后续重试
        self._should_continue = should_continue or (lambda: True)
        self.poll_interval = 1.0  # 订单状态轮询间隔（秒）

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def execute(
        self,
        signal: Signal,
        order_type_policy: str = LMT_THEN_MKT,
        risk: Optional[Dict[str, Any]] = None,
    ) -> ExecutionReportData:
        """执行一条信号直至终态，返回最终回执。"""
        raw_legs = list(signal.legs or [])
        # 多腿且券商不支持组合：在规范化（会把 symbol 改成第一腿）之前拦截，避免误下单
        if len(raw_legs) > 1 and not self.adapter.supports_combined_order():
            return self._report(
                signal,
                OrderStatus.REJECTED,
                attempt=1,
                error=(
                    f"{self.broker} 不支持多腿组合单（如 PCS/垂直价差）。"
                    "请改用支持组合的券商，或改为单腿信号。"
                ),
            )

        signal = normalize_option_signal(signal)
        cfg = signal.execution_config or ExecutionConfig()
        max_attempts = max(1, cfg.max_retry_attempts)
        multi_leg = bool(signal.legs and len(signal.legs) > 1)
        has_price = self._has_usable_price(signal)
        # 限价尝试次数：
        # - 没传限价 → 一律 0，直接市价（含 LMT_then_MKT）
        # - MKT_only：多腿且有限价时仍先试一次限价（老虎收入型价差需要）
        # - LMT_then_MKT：用配置的 limit_order_attempts；多腿有限价时至少 1 次
        if not has_price:
            limit_attempts = 0
        elif order_type_policy == MKT_ONLY:
            limit_attempts = 1 if multi_leg else 0
        else:
            limit_attempts = max(0, int(cfg.limit_order_attempts or 0))
            if multi_leg:
                limit_attempts = max(limit_attempts, 1)

        if order_type_policy == LMT_THEN_MKT and not has_price:
            logger.info(
                "信号无可用限价，LMT_then_MKT 直接走市价 signal_id=%s",
                signal.signal_id,
            )

        last_report: Optional[ExecutionReportData] = None

        for attempt in range(1, max_attempts + 1):
            if not self._should_continue():
                return self._report(signal, OrderStatus.CANCELLED, attempt=attempt,
                                     error="已暂停(kill switch)")

            use_limit = attempt <= limit_attempts and has_price
            order_type = "LMT" if use_limit else "MKT"
            order_signal = self._build_order_signal(signal, order_type)

            logger.info(
                "执行 %s 第%d/%d 次, 类型=%s, broker=%s",
                signal.signal_id, attempt, max_attempts, order_type, self.broker,
            )

            # 1) 下单
            try:
                result = self.adapter.place_order(order_signal)
            except Exception as e:  # noqa: BLE001
                logger.exception("下单异常: %s", signal.signal_id)
                err = str(e)
                last_report = self._report(signal, OrderStatus.REJECTED, attempt=attempt,
                                           order_type=order_type, error=err)
                if self._is_non_retryable_error(err):
                    return last_report
                self._sleep(1.0)
                continue

            order_id, submit_ok = self._parse_place_result(result)
            if not submit_ok:
                err = (result or {}).get("error") if isinstance(result, dict) else "下单失败"
                retryable = True
                if isinstance(result, dict) and result.get("retryable") is False:
                    retryable = False
                if self._is_non_retryable_error(str(err or "")):
                    retryable = False
                last_report = self._report(signal, OrderStatus.REJECTED, attempt=attempt,
                                           order_type=order_type, order_id=order_id, error=err)
                if not retryable:
                    logger.warning(
                        "不可重试的下单失败，停止后续尝试 signal_id=%s attempt=%s err=%s",
                        signal.signal_id, attempt, err,
                    )
                    return last_report
                self._sleep(1.0)
                continue

            # 提交成功
            self._report(signal, OrderStatus.SUBMITTED, attempt=attempt,
                         order_type=order_type, order_id=order_id)

            # 2) 超时轮询订单状态
            final_status, fill = self._wait_for_fill(order_id, cfg.order_wait_timeout)
            last_report = self._report(
                signal, final_status, attempt=attempt, order_type=order_type,
                order_id=order_id, fill=fill,
            )

            if is_success_status(final_status):
                self._maybe_place_protective(signal, last_report, risk)
                return last_report
            if final_status == OrderStatus.PARTIALLY_FILLED:
                self._maybe_place_protective(signal, last_report, risk)
                return last_report

            # IBKR 等会短暂误报 Cancelled（TIF 警告）；重试前再核对成交/存活，避免连环下单
            if final_status == OrderStatus.CANCELLED and order_id:
                reconciled = self._reconcile_after_cancel(order_id, cfg.order_wait_timeout)
                if reconciled is not None:
                    status2, fill2 = reconciled
                    last_report = self._report(
                        signal, status2, attempt=attempt, order_type=order_type,
                        order_id=order_id, fill=fill2,
                    )
                    if is_success_status(status2) or status2 == OrderStatus.PARTIALLY_FILLED:
                        self._maybe_place_protective(signal, last_report, risk)
                        return last_report
                    if not is_terminal_status(status2):
                        # 订单仍在途：继续等同一单，不再 place_order
                        final_status, fill = self._wait_for_fill(order_id, cfg.order_wait_timeout)
                        last_report = self._report(
                            signal, final_status, attempt=attempt, order_type=order_type,
                            order_id=order_id, fill=fill,
                        )
                        if is_success_status(final_status) or final_status == OrderStatus.PARTIALLY_FILLED:
                            self._maybe_place_protective(signal, last_report, risk)
                            return last_report

            # 3) 未成交：必须确认上一笔已清掉，再进入下一轮（LMT→MKT / 撤单重下）
            # EXPIRED 多为轮询超时、券商侧仍挂单；误报 CANCELLED 时也可能仍存活。
            cleared, status_after, fill_after = self._clear_order_before_retry(
                order_id, final_status
            )
            if self._has_fill(fill_after) or is_success_status(status_after) or (
                status_after == OrderStatus.PARTIALLY_FILLED
            ):
                last_report = self._report(
                    signal, status_after, attempt=attempt, order_type=order_type,
                    order_id=order_id, fill=fill_after,
                )
                self._maybe_place_protective(signal, last_report, risk)
                return last_report
            if not cleared:
                logger.error(
                    "上一笔订单未能确认撤销，停止重下以防重复下单 "
                    "signal_id=%s order_id=%s status=%s",
                    signal.signal_id, order_id, status_after.value,
                )
                return self._report(
                    signal, status_after, attempt=attempt, order_type=order_type,
                    order_id=order_id, fill=fill_after,
                    error="上一笔订单仍存活，已停止重下以防重复下单",
                )
            # 进入下一 attempt

        # 所有尝试用尽
        return last_report or self._report(signal, OrderStatus.EXPIRED, attempt=max_attempts,
                                            error="重试次数用尽未成交")

    # ------------------------------------------------------------------
    # 轮询 / 查询
    # ------------------------------------------------------------------
    def _wait_for_fill(self, order_id: Optional[str], timeout: int) -> tuple[OrderStatus, Dict[str, Any]]:
        """在 timeout 秒内轮询订单状态，返回 (状态, 成交信息)。"""
        deadline = self._now() + max(1, timeout)
        last_status = OrderStatus.PENDING
        fill: Dict[str, Any] = {}
        while self._now() < deadline:
            if not self._should_continue():
                return OrderStatus.CANCELLED, fill
            status, fill = self._query_order(order_id)
            last_status = status
            if is_terminal_status(status):
                return status, fill
            self._sleep(self.poll_interval)
        # 超时后再查一次，避免券商回报延迟导致长期 UNKNOWN/PENDING
        if order_id:
            self._sleep(1.0)
            status, fill = self._query_order(order_id)
            if self._has_fill(fill):
                return OrderStatus.FILLED, fill
            if is_terminal_status(status):
                return status, fill
            if status != OrderStatus.UNKNOWN:
                last_status = status
        if not is_terminal_status(last_status):
            return OrderStatus.EXPIRED, fill
        return last_status, fill

    @staticmethod
    def _has_fill(fill: Dict[str, Any]) -> bool:
        qty = fill.get("filled_qty") or fill.get("filled_quantity") or fill.get("filled") or 0
        try:
            return int(float(qty)) > 0
        except (TypeError, ValueError):
            return False

    def _query_order(self, order_id: Optional[str]) -> tuple[OrderStatus, Dict[str, Any]]:
        """查询单个订单状态；优先 adapter.get_order，否则从 get_orders 列表匹配。"""
        status, fill, _found = self._query_order_ex(order_id)
        return status, fill

    def _query_order_ex(
        self, order_id: Optional[str]
    ) -> tuple[OrderStatus, Dict[str, Any], bool]:
        """同 _query_order，额外返回是否在券商侧查到该订单。"""
        if not order_id:
            return OrderStatus.UNKNOWN, {}, False
        get_one = getattr(self.adapter, "get_order", None)
        if callable(get_one):
            try:
                od = get_one(str(order_id))
                if od:
                    st, fill = self._order_dict_to_status(od)
                    return st, fill, True
            except Exception as e:  # noqa: BLE001
                logger.warning("get_order 失败 order_id=%s: %s", order_id, e)
        try:
            orders = self.adapter.get_orders() or []
        except Exception as e:  # noqa: BLE001
            logger.warning("查询订单失败: %s", e)
            return OrderStatus.UNKNOWN, {}, False

        for od in orders:
            oid = str(od.get("order_id") or od.get("id") or "")
            if oid and oid == str(order_id):
                st, fill = self._order_dict_to_status(od)
                return st, fill, True
        # 已提交的单查不到时保持 PENDING 继续轮询，勿当终态去重下
        return OrderStatus.PENDING, {}, False

    def _reconcile_after_cancel(
        self, order_id: str, timeout: int
    ) -> Optional[tuple[OrderStatus, Dict[str, Any]]]:
        """Cancelled 后短暂等待再查：有成交则成功；仍存活则返回非终态。"""
        self._sleep(1.5)
        status, fill = self._query_order(order_id)
        if self._has_fill(fill):
            if status == OrderStatus.PARTIALLY_FILLED:
                return status, fill
            return OrderStatus.FILLED, fill
        if is_success_status(status) or status == OrderStatus.PARTIALLY_FILLED:
            return status, fill
        if status not in (
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.UNKNOWN,
        ):
            logger.warning(
                "订单 %s 曾报 Cancelled，复核为 %s，继续跟踪同一订单（不重下）",
                order_id, status.value,
            )
            return status, fill
        # 仍为取消：再给一次短窗口，避免 fills 延迟
        deadline = self._now() + min(5, max(1, timeout // 10 or 1))
        while self._now() < deadline:
            self._sleep(self.poll_interval)
            status, fill = self._query_order(order_id)
            if self._has_fill(fill) or is_success_status(status) or status == OrderStatus.PARTIALLY_FILLED:
                return (OrderStatus.FILLED if self._has_fill(fill) and status != OrderStatus.PARTIALLY_FILLED else status), fill
            if status not in (
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
                OrderStatus.UNKNOWN,
                OrderStatus.PENDING,
            ):
                return status, fill
        return OrderStatus.CANCELLED, fill

    def _order_dict_to_status(self, od: Dict[str, Any]) -> tuple[OrderStatus, Dict[str, Any]]:
        raw = (
            od.get("order_status")
            or od.get("status")
            or od.get("order_status_raw")
            or od.get("broker_status")
            or ""
        )
        # 适配器已归一化时优先用标准状态字段，避免 Cancelled 盖住有成交。
        # IBKR/Futu 用 std_status；Tiger 历史字段名为 standard_status。
        std_raw = od.get("std_status") or od.get("standard_status")
        if std_raw:
            status = self._normalize_status(std_raw)
        else:
            status = self._normalize_status(raw)
        fill = {
            "fill_price": od.get("filled_price") or od.get("fill_price") or od.get("avg_fill_price"),
            "filled_qty": od.get("filled_quantity") or od.get("filled_qty") or od.get("filled"),
            "amount": od.get("filled_amount") or od.get("amount"),
            "realized_pnl": od.get("realized_pnl") or od.get("realized_pl"),
        }
        if self._has_fill(fill) and status in (
            OrderStatus.PENDING,
            OrderStatus.UNKNOWN,
            OrderStatus.SUBMITTED,
            OrderStatus.NEW,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED,
        ):
            remaining = od.get("remaining")
            try:
                rem = float(remaining) if remaining is not None else 0.0
            except (TypeError, ValueError):
                rem = 0.0
            status = OrderStatus.PARTIALLY_FILLED if rem > 0 else OrderStatus.FILLED
        return status, fill

    @staticmethod
    def _normalize_status(raw: Any) -> OrderStatus:
        if isinstance(raw, OrderStatus):
            return raw
        return get_status_from_string(str(raw))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _safe_cancel(self, order_id: Optional[str]) -> bool:
        if not order_id:
            return True
        try:
            ok = self.adapter.cancel_order(str(order_id))
            # 部分适配器无返回值；False 表示明确失败
            return ok is not False
        except Exception as e:  # noqa: BLE001
            logger.warning("撤单失败 %s: %s", order_id, e)
            return False

    def _is_inactive_order_status(self, status: OrderStatus) -> bool:
        return status in (
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    def _clear_order_before_retry(
        self, order_id: Optional[str], status: OrderStatus
    ) -> tuple[bool, OrderStatus, Dict[str, Any]]:
        """重试前确认上一笔已清掉。

        Returns:
            (cleared, status, fill)
            - cleared=True：可安全进入下一 attempt（无 order_id / 已拒绝 / 已确认撤销）
            - cleared=False：订单仍可能存活，禁止再 place_order
            - 若撤单过程中发现成交，cleared=True 且 status 为 FILLED/PARTIALLY_FILLED
        """
        if not order_id:
            return True, status, {}
        if status == OrderStatus.REJECTED:
            return True, status, {}

        # CANCELLED 也再撤一次：应对误报 Cancelled 而订单仍挂着（幂等）
        logger.info(
            "重试前撤单 order_id=%s status=%s broker=%s",
            order_id, status.value, self.broker,
        )
        cancel_ok = self._safe_cancel(order_id)
        if not cancel_ok:
            logger.warning(
                "撤单接口返回失败，将复核查单状态 order_id=%s", order_id
            )

        # 短轮询确认：成交 / 已终态撤废 / 仍存活
        # 注意：查不到时 _query_order 会返回 PENDING（等待语义），须用 found 区分「真挂着」。
        deadline = self._now() + 3.0
        last_status = status
        fill: Dict[str, Any] = {}
        not_found_polls = 0
        while self._now() < deadline:
            self._sleep(0.5)
            last_status, fill, found = self._query_order_ex(order_id)
            if self._has_fill(fill):
                if last_status == OrderStatus.PARTIALLY_FILLED:
                    return True, last_status, fill
                return True, OrderStatus.FILLED, fill
            if is_success_status(last_status) or last_status == OrderStatus.PARTIALLY_FILLED:
                return True, last_status, fill
            if self._is_inactive_order_status(last_status):
                return True, last_status, fill
            if not found:
                not_found_polls += 1
                if not_found_polls >= 2:
                    return True, OrderStatus.CANCELLED, fill
                continue
            not_found_polls = 0

        if self._has_fill(fill) or is_success_status(last_status) or (
            last_status == OrderStatus.PARTIALLY_FILLED
        ):
            return True, last_status, fill
        if self._is_inactive_order_status(last_status):
            return True, last_status, fill
        if not_found_polls >= 1 and cancel_ok:
            return True, OrderStatus.CANCELLED, fill
        logger.error(
            "撤单后订单仍非终态 order_id=%s status=%s cancel_ok=%s",
            order_id, last_status.value, cancel_ok,
        )
        return False, last_status, fill

    def _maybe_place_protective(
        self,
        signal: Signal,
        report: ExecutionReportData,
        risk: Optional[Dict[str, Any]],
    ) -> None:
        if not risk or not report.fill_price:
            return
        sl = risk.get("stop_loss_pct")
        tp = risk.get("take_profit_pct")
        if sl is None and tp is None:
            return
        try:
            result = self.adapter.place_protective_orders(
                signal,
                float(report.fill_price),
                stop_loss_pct=sl,
                take_profit_pct=tp,
            )
            status = result.get("status")
            if status not in ("skipped", None):
                logger.info("protective orders placed: %s", result)
            if status == "FAILED":
                # 已成交但保护单失败：用户持仓无 SL/TP，必须显式告警。
                self._report_protective_failure(signal, report, result.get("error") or "protective failed")
        except Exception as e:  # noqa: BLE001
            logger.warning("protective orders failed: %s", e)
            self._report_protective_failure(signal, report, str(e))

    def _report_protective_failure(self, signal: Signal, report: ExecutionReportData, error: str) -> None:
        if not self.on_report:
            return
        rpt = ExecutionReportData(
            signal_id=signal.signal_id,
            source_id=self.source_id,
            broker=self.broker,
            account_id=self.account_id,
            status="protective_failed",
            order_id=report.order_id,
            symbol=signal.symbol,
            side=signal.action or None,
            asset_type=signal.asset_class,
            quantity=float(signal.quantity) if signal.quantity else None,
            fill_price=report.fill_price,
            timestamp=self._now(),
            error=error,
        )
        try:
            self.on_report(rpt)
        except Exception:  # noqa: BLE001
            logger.exception("on_report 回调异常")

    @staticmethod
    def _has_usable_price(signal: Signal) -> bool:
        if signal.limit_price is not None:
            return True
        if signal.legs:
            return any(getattr(leg, "limit_price", None) for leg in signal.legs)
        return False

    @staticmethod
    def _is_non_retryable_error(err: str) -> bool:
        """结构性/权限类失败不应再 LMT→MKT 或反复重下。"""
        text = (err or "").strip()
        if not text:
            return False
        lower = text.lower()
        # 真正频控（code=5）可短重试；「请稍后再试」多为盘外/暂不可交易，勿连打 5 次
        if "code=5" in lower or "rate limit error" in lower or "too many requests" in lower:
            return False
        if "请稍后再试" in text or "try again later" in lower:
            return True
        needles = (
            "不支持多腿",
            "不支持组合",
            "无法交易",
            "不可交易",
            "合约不正确",
            "未连接",
            "凭证",
            "权限不足",
            "缺少 limit_price",
            "us_index",
            "index asset class",
            "not supported",
            "unsupported",
            "not tradable",
            "cannot trade",
            "permission",
            "unauthorized",
            "invalid symbol",
            "invalid contract",
            "bad_request",
        )
        return any(n in text or n in lower for n in needles)

    @staticmethod
    def _build_order_signal(signal: Signal, order_type: str) -> Signal:
        """复制信号并设置本次尝试的订单类型；MKT 时清空限价。"""
        import copy

        s = copy.copy(signal)
        s.order_type = order_type
        if order_type == "MKT":
            s.limit_price = None
        return s

    @staticmethod
    def _parse_place_result(result: Any) -> tuple[Optional[str], bool]:
        if not isinstance(result, dict):
            return None, False
        order_id = result.get("order_id") or result.get("id")
        status = str(result.get("status", "")).upper()
        ok = status in ("SUCCESS", "SUBMITTED", "OK", "FILLED") or bool(order_id and status not in ("ERROR", "FAILED", "REJECTED"))
        return (str(order_id) if order_id else None), ok

    def _report(
        self,
        signal: Signal,
        status: OrderStatus,
        attempt: int = 1,
        order_type: Optional[str] = None,
        order_id: Optional[str] = None,
        fill: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> ExecutionReportData:
        fill = fill or {}
        rpt = ExecutionReportData(
            signal_id=signal.signal_id,
            source_id=self.source_id,
            broker=self.broker,
            account_id=self.account_id,
            status=status.value if isinstance(status, OrderStatus) else str(status),
            order_id=order_id or signal.order_id,
            symbol=signal.symbol,
            side=signal.action or None,
            asset_type=signal.asset_class,
            quantity=float(signal.quantity) if signal.quantity else None,
            limit_price=signal.limit_price if order_type == "LMT" else None,
            fill_price=fill.get("fill_price"),
            filled_qty=fill.get("filled_qty"),
            amount=fill.get("amount"),
            realized_pnl=fill.get("realized_pnl"),
            attempt=attempt,
            timestamp=self._now(),
            error=error,
        )
        if self.on_report:
            try:
                self.on_report(rpt)
            except Exception:  # noqa: BLE001
                logger.exception("on_report 回调异常")
        return rpt
