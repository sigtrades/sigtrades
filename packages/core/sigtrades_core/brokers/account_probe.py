"""券商账户连通性探测：统一 connect + get_account_info，并归一化摘要。

各券商 SDK/REST 字段不同；UI / API 只消费本模块输出的 AccountProbeResult。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from sigtrades_core.brokers import BROKER_DEPLOYMENT, create_broker_adapter

logger = logging.getLogger(__name__)

CLOUD_PROBE_BROKERS = frozenset(
    name for name, side in BROKER_DEPLOYMENT.items() if side == "cloud"
)


@dataclass
class AccountProbeResult:
    ok: bool
    broker: str
    account_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_account_summary(broker: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """把各券商 get_account_info 原始结构压成统一摘要。"""
    key = (broker or "").strip().lower()
    summary: Dict[str, Any] = {
        "account_id": info.get("account_id") or info.get("account") or info.get("id"),
        "net_liquidation": None,
        "available_cash": None,
        "currency": info.get("currency") or "USD",
        "is_paper": info.get("is_paper"),
    }

    if key == "tiger":
        summary["account_id"] = info.get("account_id") or info.get("account")
        summary["net_liquidation"] = _num(info.get("net_liquidation") or info.get("total_assets"))
        summary["available_cash"] = _num(info.get("available_cash"))
        summary["is_paper"] = bool(info.get("is_paper"))
        return summary

    if key == "alpaca":
        summary["account_id"] = info.get("account_number") or info.get("id")
        summary["net_liquidation"] = _num(info.get("equity") or info.get("portfolio_value"))
        summary["available_cash"] = _num(info.get("cash") or info.get("buying_power"))
        summary["currency"] = info.get("currency") or "USD"
        summary["is_paper"] = str(info.get("account_number") or "").startswith("PA") or None
        return summary

    if key == "longbridge":
        balances = info.get("balances") or []
        usd = next((b for b in balances if str(b.get("currency") or "").upper() == "USD"), None)
        pick = usd or (balances[0] if balances else {})
        summary["net_liquidation"] = _num(pick.get("net_assets"))
        summary["available_cash"] = _num(pick.get("total_cash") or pick.get("buy_power"))
        summary["currency"] = pick.get("currency") or "USD"
        summary["is_paper"] = str(info.get("env") or "").lower() in ("sandbox", "test", "paper")
        return summary

    if key == "schwab":
        # schwab adapter 通常返回账户 JSON；兼容嵌套 securitiesAccount
        acct = info.get("securitiesAccount") or info
        balances = acct.get("currentBalances") or acct.get("initialBalances") or {}
        summary["account_id"] = acct.get("accountNumber") or info.get("account_id")
        summary["net_liquidation"] = _num(
            balances.get("liquidationValue")
            or balances.get("accountValue")
            or info.get("net_liquidation")
        )
        summary["available_cash"] = _num(
            balances.get("cashBalance")
            or balances.get("availableFunds")
            or info.get("available_cash")
        )
        return summary

    if key == "usmart":
        summary["account_id"] = info.get("account_id") or info.get("fundAccount")
        summary["net_liquidation"] = _num(info.get("net_liquidation") or info.get("totalAsset"))
        summary["available_cash"] = _num(info.get("available_cash") or info.get("enableBalance"))
        summary["currency"] = info.get("currency") or "USD"
        summary["is_paper"] = bool(info.get("is_paper")) or str(info.get("env") or "").lower() == "uat"
        return summary

    if key == "ibkr_web":
        summary["account_id"] = info.get("account_id") or info.get("account")
        summary["net_liquidation"] = _num(info.get("net_liquidation"))
        summary["available_cash"] = _num(info.get("available_cash"))
        summary["currency"] = info.get("currency") or "USD"
        summary["is_paper"] = bool(info.get("is_paper")) or str(info.get("env") or "").lower() in (
            "paper",
            "test",
            "sandbox",
        )
        return summary

    # ibkr / futu / 未知：尽量从常见字段抽取
    summary["net_liquidation"] = _num(
        info.get("net_liquidation") or info.get("total_assets") or info.get("NetLiquidation")
    )
    summary["available_cash"] = _num(
        info.get("available_cash") or info.get("cash") or info.get("TotalCashValue")
    )
    return summary


def probe_broker_account(broker: str, config: Dict[str, Any]) -> AccountProbeResult:
    """同步探测：创建适配器 → connect → get_account_info → disconnect。"""
    key = (broker or "").strip().lower()
    if key not in CLOUD_PROBE_BROKERS:
        return AccountProbeResult(
            ok=False,
            broker=key,
            error="该券商需通过本地 Agent（IBKR/富途）连接，云端无法直接测账户",
        )
    adapter = None
    try:
        adapter = create_broker_adapter(key, config)
        if not adapter.connect():
            err = getattr(adapter, "connect_error", None) or "券商连接失败"
            return AccountProbeResult(ok=False, broker=key, error=str(err))
        info = adapter.get_account_info() or {}
        if not isinstance(info, dict):
            info = {"raw": info}
        summary = normalize_account_summary(key, info)
        # 至少要有净值或可用资金之一，才视为「拿到有效账户信息」
        if summary.get("net_liquidation") is None and summary.get("available_cash") is None:
            return AccountProbeResult(
                ok=False,
                broker=key,
                account_summary=summary,
                error="已连接但未返回可用资金/净值信息",
            )
        return AccountProbeResult(ok=True, broker=key, account_summary=summary, error=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("probe_broker_account failed broker=%s", key)
        return AccountProbeResult(ok=False, broker=key, error=str(exc))
    finally:
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception:  # noqa: BLE001
                pass
