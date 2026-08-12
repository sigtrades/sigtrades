"""期权符号规范化：解析 → 结构化字段 → 各券商合约格式。

解析层输出可以是简写（如 ``SPY 758C``，无到期日），执行前在此补全并转为
券商 API 所需的 ``标的 + 到期日 + 行权价 + 方向``。
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
from zoneinfo import ZoneInfo

from sigtrades_core.signal.models import OptionLeg, Signal

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")

# SPY 758C / SPY 758 C
_SHORT_STRIKE_RIGHT = re.compile(r"^(\d+(?:\.\d+)?)\s*([CP])$", re.I)
# SPY 240119C450 / SPXW 250519P05910000 / AAPL 260626C00297500
_FULL_OPTION_TAIL = re.compile(r"^(\d{6})([CP])(\d+(?:\.\d+)?)$", re.I)
# OCC 紧凑：AAPL250117P00200000 / SPXW250721P07450000（无空格）
_OCC_COMPACT = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$", re.I)
# SPY758C（无空格）
_COMPACT = re.compile(r"^([A-Z][A-Z0-9]*)(\d+(?:\.\d+)?)([CP])$", re.I)


def _strike_from_occ_digits(strike_str: str) -> float:
    """OCC 行权价编码：8 位整数 = strike × 1000。"""
    digits = (strike_str or "").strip()
    if not digits:
        return 0.0
    if len(digits) >= 8 or (digits.isdigit() and len(digits) >= 5):
        return float(digits.lstrip("0") or "0") / 1000
    return float(digits)


def _parsed_from_yymmdd(und: str, yymmdd: str, right: str, strike: float) -> ParsedOption:
    yy, mm, dd = yymmdd[:2], yymmdd[2:4], yymmdd[4:6]
    year = f"20{yy}"
    expiry_contract = f"{year}{mm}{dd}"
    expiry_date = f"{year}-{mm}-{dd}"
    opt = right.upper()
    return ParsedOption(
        underlying=und.upper(),
        strike=strike,
        right=opt,
        put_call=_put_call(opt),
        expiry=expiry_date,
        expiry_contract=expiry_contract,
    )


@dataclass
class ParsedOption:
    underlying: str
    strike: float
    right: str  # C / P
    put_call: str  # CALL / PUT
    expiry: str  # YYYY-MM-DD
    expiry_contract: str  # YYYYMMDD

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.underlying,
            "underlying": self.underlying,
            "strike": self.strike,
            "right": self.right,
            "put_call": self.put_call,
            "expiry": self.expiry,
            "expiry_contract": self.expiry_contract,
        }


def today_expiry_et() -> tuple[str, str]:
    """美东当日日期，用于 0DTE 缺省到期日。"""
    return expiry_from_dte(0)


def expiry_from_dte(dte: int = 0) -> tuple[str, str]:
    """美东时区：今日 + dte 天作为期权到期日。"""
    now = datetime.now(NY)
    target = now + timedelta(days=max(0, int(dte)))
    return target.strftime("%Y-%m-%d"), target.strftime("%Y%m%d")


def _normalize_right(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().upper()
    if key in ("C", "CALL"):
        return "C"
    if key in ("P", "PUT"):
        return "P"
    return None


def _put_call(right: str) -> str:
    return "CALL" if right.upper() == "C" else "PUT"


def _parse_expiry_hint(raw: Any) -> Optional[tuple[str, str]]:
    if raw is None:
        return None
    text = str(raw).strip().replace("-", "").replace("/", "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}", text
    if len(text) == 6 and text.isdigit():
        full = f"20{text}"
        return f"{full[:4]}-{full[4:6]}-{full[6:8]}", full
    return None


def format_broker_option_symbol(parsed: ParsedOption) -> str:
    """``SPY 240119C00450000`` 风格（YYMMDD + C/P + 8 位行权价，×1000 编码）。"""
    yy = parsed.expiry_contract[2:]
    strike_str = f"{int(round(parsed.strike * 1000)):08d}"
    return f"{parsed.underlying} {yy}{parsed.right.upper()}{strike_str}"


def format_schwab_option_symbol(parsed: ParsedOption) -> str:
    """Schwab/OCC: 6 位标的 + YYMMDD + C/P + 8 位行权价。

    Example: ``AAPL  260626C00297500``.
    """
    underlying = parsed.underlying.strip().upper()
    if not underlying or len(underlying) > 6:
        raise ValueError(f"invalid Schwab option underlying: {parsed.underlying}")
    yy = parsed.expiry_contract[2:]
    strike_str = f"{int(round(parsed.strike * 1000)):08d}"
    return f"{underlying:<6}{yy}{parsed.right.upper()}{strike_str}"


def format_tiger_option_identifier(parsed: ParsedOption) -> str:
    """老虎 OCC 21 位 identifier（与 Schwab 相同）：``SPY   260724P00600000``。

    标的右补空格至 6 位 + YYMMDD + C/P + strike×1000（8 位）。
    四要素下单（symbol/expiry/strike/put_call）时可不传 identifier，
    但日志/校验/SDK ``get_option_identifier`` 应对齐此格式。
    """
    return format_schwab_option_symbol(parsed)


def format_alpaca_option_symbol(parsed: ParsedOption) -> str:
    """Alpaca compact OCC: ``AAPL260626C00297500``."""
    underlying = parsed.underlying.strip().upper()
    if not underlying:
        raise ValueError("invalid Alpaca option underlying")
    yy = parsed.expiry_contract[2:]
    strike_str = f"{int(round(parsed.strike * 1000)):08d}"
    return f"{underlying}{yy}{parsed.right.upper()}{strike_str}"


# 富途美股「指数本身」用 ``US..``（双点），如 US..SPX；见 OpenAPI Q15。
# 注意：指数**期权**实测必须用单点 ``US.SPXW...``——文档示例 US..SPXW... 会被
# OpenD basicinfo / place_combo_order 判为「未知股票」。
FUTU_US_INDEX_UNDERLYINGS = frozenset({
    "SPX",
    "SPXW",
    "XSP",
    "NDX",
    "NDXP",
    "RUT",
    "RUTW",
    "VIX",
    "VIXW",
    "DJX",
})


def format_futu_option_code(parsed: ParsedOption) -> str:
    """Futu OpenAPI 期权代码。

    - 股票/ETF：``US.NVDA260330C160000``
    - 指数期权：``US.SPXW260729P7370000``（单点；勿用 US..）
    - 行权价 = round(strike × 1000)，**不补前导零**（与 OCC 8 位不同）
    """
    underlying = (parsed.underlying or "").strip().upper()
    if not underlying:
        raise ValueError("invalid Futu option underlying")
    expiry_short = parsed.expiry_contract[2:]
    type_char = parsed.right.upper()
    strike_str = str(int(round(parsed.strike * 1000)))
    # 期权一律 US.；US.. 仅用于指数现货代码（非本函数职责）
    return f"US.{underlying}{expiry_short}{type_char}{strike_str}"


def format_longbridge_option_symbol(parsed: ParsedOption, *, region: str = "US") -> str:
    """长桥期权代码：``AAPL260626C297500.US``、``CIFR260618C27500.US``。

    行权价 = round(strike × 1000)，**不补前导零**（与老虎/OCC 8 位编码不同）。
    官方文档建议通过 option chain API 获取 ``call_symbol`` / ``put_symbol``。
    """
    yy = parsed.expiry_contract[2:]
    strike_str = str(int(round(parsed.strike * 1000)))
    return f"{parsed.underlying}{yy}{parsed.right.upper()}{strike_str}.{region}"


def format_option_for_broker(broker: str, parsed: ParsedOption, *, region: str = "US") -> str:
    """按券商规则输出期权代码（下单/展示用）。

    | 券商 | 格式 |
    |------|------|
    | tiger / schwab | 21 位 OCC，标的右填空格至 6：``SPY   260724P00680000`` |
    | alpaca | 紧凑 OCC，无空格：``SPY260724P00680000`` |
    | futu | 股票/ETF ``US.SPY260724P680000``；指数期权 ``US.SPXW260729P7370000`` |
    | longbridge | 行权价不补零：``SPY260724P680000.US`` |
    | ibkr | 不走字符串代码，用标的+到期+行权价+权利四要素；此处返回紧凑 OCC 供日志 |
    """
    key = (broker or "").strip().lower()
    if key in ("tiger", "schwab"):
        return format_tiger_option_identifier(parsed)
    if key == "alpaca":
        return format_alpaca_option_symbol(parsed)
    if key == "futu":
        return format_futu_option_code(parsed)
    if key in ("longbridge", "long_bridge", "lb"):
        return format_longbridge_option_symbol(parsed, region=region)
    # IBKR / 未知：紧凑 OCC，便于日志对照
    return format_alpaca_option_symbol(parsed)


def format_longbridge_stock_symbol(symbol: str, *, region: str = "US") -> str:
    """长桥股票代码：``AAPL.US``。"""
    base = (symbol or "").strip().upper().split()[0]
    if not base:
        raise ValueError("empty stock symbol")
    if "." in base:
        return base
    return f"{base}.{region}"


def _hints_from_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    meta = metadata or {}
    dte = meta.get("dte")
    if dte is not None:
        try:
            dte = int(dte)
        except (TypeError, ValueError):
            dte = None
    return {
        "underlying": meta.get("underlying") or meta.get("ticker"),
        "strike": meta.get("strike"),
        "right": _normalize_right(meta.get("right") or meta.get("option_type")),
        "expiry": meta.get("expiry") or meta.get("expiry_date"),
        "dte": dte,
    }


def _resolve_default_expiry(
    exp_hint: Optional[tuple[str, str]],
    *,
    dte: Optional[int] = None,
    default_dte: Optional[int] = None,
    default_expiry_today: bool = True,
    context: str = "",
) -> tuple[str, str]:
    if exp_hint:
        return exp_hint
    if dte is not None:
        return expiry_from_dte(dte)
    if default_dte is not None:
        return expiry_from_dte(default_dte)
    if default_expiry_today:
        return today_expiry_et()
    raise ValueError(f"简写期权缺少到期日: {context}".strip())


def _is_option_signal_dict(signal: Dict[str, Any]) -> bool:
    ac = (signal.get("asset_class") or "").upper()
    if ac == "STOCK":
        return False
    if ac in ("OPTIONS", "STOCK_OPTIONS", "SPX_OPTIONS"):
        return True
    meta = signal.get("metadata") or {}
    if meta.get("strike") is not None and meta.get("right"):
        return True
    sym = (signal.get("symbol") or "").strip()
    if not sym:
        return False
    upper = sym.upper()
    if " " not in sym:
        return bool(_OCC_COMPACT.match(upper) or _COMPACT.match(upper))
    tail = sym.split()[-1].upper().replace(" ", "")
    return bool(_SHORT_STRIKE_RIGHT.match(tail) or _FULL_OPTION_TAIL.match(tail))


def _symbol_has_embedded_expiry(symbol: str) -> bool:
    parts = symbol.strip().split()
    if len(parts) != 2:
        return False
    return bool(_FULL_OPTION_TAIL.match(parts[1].upper().replace(" ", "")))


def apply_source_option_dte(signal: Dict[str, Any], option_default_dte: Optional[int]) -> Dict[str, Any]:
    """信号源级 DTE：解析出期权且无到期日时，写入 metadata.dte / expiry。"""
    if option_default_dte is None or not _is_option_signal_dict(signal):
        return signal
    meta = dict(signal.get("metadata") or {})
    if meta.get("expiry") or meta.get("expiry_date"):
        return signal
    sym = (signal.get("symbol") or "").strip()
    if sym and _symbol_has_embedded_expiry(sym):
        return signal
    meta["dte"] = int(option_default_dte)
    expiry_date, expiry_contract = expiry_from_dte(int(option_default_dte))
    meta["expiry"] = expiry_date
    meta["expiry_contract"] = expiry_contract
    signal["metadata"] = meta
    return signal


def parse_option_symbol(
    option_symbol: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    underlying: Optional[str] = None,
    strike: Optional[Union[int, float]] = None,
    right: Optional[str] = None,
    expiry: Optional[str] = None,
    default_expiry_today: bool = True,
    default_dte: Optional[int] = None,
) -> Dict[str, Any]:
    """解析期权符号为统一 dict（兼容各券商 adapter 既有接口）。

    支持：
    - 完整：``SPY 240119C450``、``SPXW 250519P05910000``
    - OCC 紧凑：``AAPL250117P00200000``、``SPXW250721P07450000``
    - 简写：``SPY 758C``（缺到期日时默认美东当日 0DTE）
    - 结构化字段：metadata / 参数传入 underlying、strike、right、expiry
    """
    hints = _hints_from_metadata(metadata)
    und = (underlying or hints.get("underlying") or "").strip().upper() or None
    stk = strike if strike is not None else hints.get("strike")
    rt = _normalize_right(right) or hints.get("right")
    exp_hint = _parse_expiry_hint(expiry or hints.get("expiry"))
    dte_hint = hints.get("dte")

    text = (option_symbol or "").strip()
    parts = text.split() if text else []

    # --- OCC 紧凑无空格（优先于 SPY758C）---
    if text and " " not in text:
        m_occ = _OCC_COMPACT.match(text.upper())
        if m_occ:
            parsed = _parsed_from_yymmdd(
                m_occ.group(1),
                m_occ.group(2),
                m_occ.group(3),
                _strike_from_occ_digits(m_occ.group(4)),
            )
            return parsed.to_dict()

    # --- 完整两段格式 ---
    if len(parts) == 2:
        und = und or parts[0].upper()
        tail = parts[1].upper().replace(" ", "")
        m_full = _FULL_OPTION_TAIL.match(tail)
        if m_full:
            parsed = _parsed_from_yymmdd(
                und,
                m_full.group(1),
                m_full.group(2),
                _strike_from_occ_digits(m_full.group(3)),
            )
            return parsed.to_dict()

        m_short = _SHORT_STRIKE_RIGHT.match(tail)
        if m_short:
            parsed_strike = float(m_short.group(1))
            opt_type = m_short.group(2).upper()
            expiry_date, expiry_contract = _resolve_default_expiry(
                exp_hint,
                dte=dte_hint,
                default_dte=default_dte,
                default_expiry_today=default_expiry_today,
                context=option_symbol,
            )
            parsed = ParsedOption(
                underlying=und,
                strike=parsed_strike,
                right=opt_type,
                put_call=_put_call(opt_type),
                expiry=expiry_date,
                expiry_contract=expiry_contract,
            )
            return parsed.to_dict()

    # --- 单段 SPY758C ---
    if len(parts) == 1:
        m_compact = _COMPACT.match(parts[0].upper())
        if m_compact:
            und = und or m_compact.group(1)
            parsed_strike = float(m_compact.group(2))
            opt_type = m_compact.group(3).upper()
            expiry_date, expiry_contract = _resolve_default_expiry(
                exp_hint,
                dte=dte_hint,
                default_dte=default_dte,
                default_expiry_today=default_expiry_today,
                context=option_symbol,
            )
            parsed = ParsedOption(
                underlying=und,
                strike=parsed_strike,
                right=opt_type,
                put_call=_put_call(opt_type),
                expiry=expiry_date,
                expiry_contract=expiry_contract,
            )
            return parsed.to_dict()

    # --- 纯结构化字段 ---
    if und and stk is not None and rt:
        parsed_strike = float(stk)
        expiry_date, expiry_contract = _resolve_default_expiry(
            exp_hint,
            dte=dte_hint,
            default_dte=default_dte,
            default_expiry_today=default_expiry_today,
            context=f"underlying={und} strike={stk} right={rt}",
        )
        parsed = ParsedOption(
            underlying=und,
            strike=parsed_strike,
            right=rt,
            put_call=_put_call(rt),
            expiry=expiry_date,
            expiry_contract=expiry_contract,
        )
        return parsed.to_dict()

    raise ValueError(f"无效的期权代码格式: {option_symbol}")


def _is_option_signal(signal: Signal) -> bool:
    """与 `_is_option_signal_dict` 对齐：显式 STOCK 永不按期权；空格 alone 不够。"""
    ac = (signal.asset_class or "").upper()
    if ac == "STOCK":
        return False
    if ac in ("OPTIONS", "STOCK_OPTIONS", "SPX_OPTIONS"):
        return True
    if signal.legs:
        return True
    meta = signal.metadata or {}
    if meta.get("strike") is not None and meta.get("right"):
        return True
    sym = (signal.symbol or "").strip()
    if not sym:
        return False
    upper = sym.upper()
    if " " not in sym:
        return bool(_OCC_COMPACT.match(upper) or _COMPACT.match(upper))
    tail = sym.split()[-1].upper().replace(" ", "")
    return bool(_SHORT_STRIKE_RIGHT.match(tail) or _FULL_OPTION_TAIL.match(tail))


def _parsed_from_dict(info: Dict[str, Any]) -> ParsedOption:
    return ParsedOption(
        underlying=info["underlying"],
        strike=float(info["strike"]),
        right=info["right"],
        put_call=info["put_call"],
        expiry=info["expiry"],
        expiry_contract=info["expiry_contract"],
    )


def _resolve_option_leg(leg: OptionLeg, meta: Dict[str, Any]) -> tuple[OptionLeg, Dict[str, Any]]:
    info = parse_option_symbol(
        leg.symbol,
        metadata=meta,
        strike=leg.strike,
        right=leg.option_type,
    )
    broker_sym = format_broker_option_symbol(_parsed_from_dict(info))
    return (
        OptionLeg(
            symbol=broker_sym,
            action=leg.action,
            quantity=leg.quantity,
            limit_price=leg.limit_price,
            strike=info["strike"],
            option_type=info["put_call"],
        ),
        info,
    )


def normalize_option_signal(signal: Signal) -> Signal:
    """执行前补全期权结构化字段，并生成单腿 legs（若缺失）。"""
    if (signal.asset_class or "").upper() == "STOCK":
        return signal
    if not _is_option_signal(signal):
        return signal

    s = copy.deepcopy(signal)
    meta = dict(s.metadata or {})
    primary_info: Dict[str, Any]

    if s.legs:
        resolved: list[OptionLeg] = []
        for leg in s.legs:
            new_leg, info = _resolve_option_leg(leg, meta)
            resolved.append(new_leg)
            primary_info = info
        s.legs = resolved
        s.symbol = resolved[0].symbol
    else:
        primary_info = parse_option_symbol(
            s.symbol,
            metadata=meta,
            underlying=meta.get("underlying"),
            strike=meta.get("strike"),
            right=meta.get("right") or meta.get("option_type"),
            expiry=meta.get("expiry") or meta.get("expiry_date"),
        )
        broker_sym = format_broker_option_symbol(_parsed_from_dict(primary_info))
        s.symbol = broker_sym
        s.legs = [
            OptionLeg(
                symbol=broker_sym,
                action=s.action or "BUY",
                quantity=s.quantity or 1,
                limit_price=s.limit_price,
                strike=primary_info["strike"],
                option_type=primary_info["put_call"],
            )
        ]

    meta.update({
        "underlying": primary_info["underlying"],
        "strike": primary_info["strike"],
        "right": primary_info["right"],
        "expiry": primary_info["expiry"],
        "expiry_contract": primary_info["expiry_contract"],
    })
    s.metadata = meta
    if not s.asset_class:
        s.asset_class = "OPTIONS"
    logger.info(
        "期权符号规范化: symbol=%s underlying=%s strike=%s right=%s expiry=%s",
        s.symbol,
        meta["underlying"],
        meta["strike"],
        meta["right"],
        meta["expiry"],
    )
    return s
