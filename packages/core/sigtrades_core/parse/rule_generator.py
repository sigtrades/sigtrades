"""从输入/输出样例自动生成解析规则。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Signal#173-SPY-758C-ENTRY-0.93
SIGNAL_HASH_PATTERN = (
    r"Signal#(\d+)-([A-Z][A-Z0-9]*)-(\d+)([CP])-(ENTRY|EXIT)-([\d.]+)"
)

# TICKER STRIKE C|P YYYY-MM-DD + $126K AVG$11.79 24DTE（期权 flow 两行块，标的/行权价/成交额均为变量）
FLOW_ALERT_PATTERN = (
    r"([A-Z][A-Z0-9]*)\s+([\d.]+)\s+([CP])\s+"
    r"(\d{4}[-/]\d{2}[-/]\d{2})\s*"
    r"(?:\r?\n)\s*"
    r"\$[\d.]+[KMB]\s+"
    r"AVG\$([\d.]+)\s+"
    r"(\d+)DTE"
)

_BOILERPLATE_LINE = re.compile(
    r"informational\s+purposes\s+only|not\s+financial\s+advice",
    re.I,
)

ACTION_ALIASES: Dict[str, List[str]] = {
    "BUY": ["BUY", "ENTRY", "LONG", "OPEN", "买入", "做多"],
    "SELL": ["SELL", "EXIT", "SHORT", "CLOSE", "卖出", "做空"],
}

SUBTYPE_ALIASES: Dict[str, List[str]] = {
    "OPEN": ["ENTRY", "OPEN", "BUY", "LONG"],
    "CLOSE": ["EXIT", "CLOSE", "SELL", "SHORT"],
}


def _find_token_for_action(sample: str, action: str) -> Optional[str]:
    upper = sample.upper()
    for token in ACTION_ALIASES.get(str(action).upper(), []):
        if token in upper:
            # Prefer whole segment match on delimiters
            for part in re.split(r"[-\s#]+", upper):
                if part == token:
                    return token
            if token in upper:
                return token
    return None


def _find_token_for_subtype(sample: str, subtype: str) -> Optional[str]:
    upper = sample.upper()
    for token in SUBTYPE_ALIASES.get(str(subtype).upper(), []):
        for part in re.split(r"[-\s#]+", upper):
            if part == token:
                return token
    return None


def _strip_boilerplate_lines(sample: str) -> str:
    """去掉免责声明等固定套话，避免写入正则字面量。"""
    kept: List[str] = []
    for line in sample.splitlines():
        if _BOILERPLATE_LINE.search(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _is_flow_alert_sample(sample: str) -> bool:
    return bool(re.search(FLOW_ALERT_PATTERN, _strip_boilerplate_lines(sample), re.I))


def flow_alert_option_config() -> Dict[str, Any]:
    """期权 flow 两行块：只按字段位置匹配，不绑定具体标的。"""
    return {
        "pattern": FLOW_ALERT_PATTERN,
        "groups": {
            "underlying": 1,
            "strike": 2,
            "right": 3,
            "expiry": 4,
            "limit_price": 5,
            "dte": 6,
        },
        "field_rules": {
            "action": {"literal": "BUY"},
            "signal_subtype": {"literal": "OPEN"},
            "symbol": {"template": "{underlying} {strike}{right}"},
            "quantity": {"literal": 1},
            "limit_price": {"from_group": "limit_price", "type": "float"},
            "order_type": {"literal": "LMT"},
            "asset_class": {"literal": "OPTIONS"},
        },
        "metadata_rules": {
            "underlying": {"from_group": "underlying"},
            "strike": {"from_group": "strike", "type": "float"},
            "right": {"from_group": "right"},
            "expiry": {"from_group": "expiry"},
            "dte": {"from_group": "dte", "type": "int"},
        },
    }


def signal_hash_option_config() -> Dict[str, Any]:
    """内置：Signal#ID-TICKER-STRIKERIGHT-ENTRY|EXIT-PRICE 期权格式。"""
    return {
        "pattern": SIGNAL_HASH_PATTERN,
        "groups": {
            "signal_ref": 1,
            "underlying": 2,
            "strike": 3,
            "right": 4,
            "event": 5,
            "limit_price": 6,
        },
        "field_rules": {
            "action": {"from_group": "event", "map": {"ENTRY": "BUY", "EXIT": "SELL"}},
            "signal_subtype": {"from_group": "event", "map": {"ENTRY": "OPEN", "EXIT": "CLOSE"}},
            "symbol": {"template": "{underlying} {strike}{right}"},
            "underlying": {"from_group": "underlying"},
            "strike": {"from_group": "strike", "type": "float"},
            "right": {"from_group": "right"},
            "quantity": {"literal": 1},
            "limit_price": {"from_group": "limit_price", "type": "float"},
            "order_type": {"literal": "LMT"},
            "asset_class": {"literal": "OPTIONS"},
        },
        "metadata_rules": {
            "signal_ref": {"from_group": "signal_ref"},
            "underlying": {"from_group": "underlying"},
            "strike": {"from_group": "strike", "type": "int"},
            "right": {"from_group": "right"},
        },
    }


def _literal_to_regex(value: str) -> str:
    return re.escape(value)


def _expected_meta(expected: Dict[str, Any]) -> Dict[str, Any]:
    meta = dict(expected.get("metadata") or {})
    for key in ("underlying", "strike", "right", "expiry", "expiry_date", "dte"):
        if key in expected and key not in meta:
            meta[key] = expected[key]
    return meta


def _float_eq(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return False


def _split_sample_parts(sample: str) -> List[str]:
    """切分样例文本，保留 YYYY-MM-DD 等完整日期 token。"""
    text = sample.strip()
    protected: List[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__DATE{len(protected) - 1}__"

    text = re.sub(r"\d{4}-\d{2}-\d{2}", _protect, text)
    text = re.sub(r"\d{4}/\d{2}/\d{2}", _protect, text)
    parts = [p for p in re.split(r"[-\s|:,]+", text) if p]
    restored: List[str] = []
    for part in parts:
        m = re.fullmatch(r"__DATE(\d+)__", part)
        restored.append(protected[int(m.group(1))] if m else part)
    return restored


def _is_boilerplate_part(part: str) -> bool:
    low = part.lower().strip(".")
    if low in {"informational", "purposes", "only", "not", "financial", "advice"}:
        return True
    return bool(_BOILERPLATE_LINE.search(part))


def _build_segment_pattern(sample: str, expected: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """按分隔符切分样例，将各段映射到输出字段。"""
    if re.search(SIGNAL_HASH_PATTERN, sample, re.I):
        return signal_hash_option_config()
    if _is_flow_alert_sample(sample):
        return flow_alert_option_config()

    sample = _strip_boilerplate_lines(sample)
    delimiters = r"[-\s|:,]+"
    parts = _split_sample_parts(sample)
    if len(parts) < 2:
        return None

    meta = _expected_meta(expected)
    used_fields: set[str] = set()
    group_map: Dict[str, int] = {}
    field_rules: Dict[str, Any] = {}
    metadata_rules: Dict[str, Any] = {}
    regex_parts: List[str] = []
    group_idx = 1

    def take_group(name: str, part_regex: str) -> str:
        nonlocal group_idx
        group_map[name] = group_idx
        group_idx += 1
        return f"({part_regex})"

    def maybe_bind_option_symbol() -> None:
        if "symbol" in used_fields:
            return
        if "underlying" not in group_map:
            return
        if "strike" in group_map and "right" in group_map:
            field_rules["symbol"] = {"template": "{underlying} {strike}{right}"}
            if expected.get("asset_class"):
                field_rules["asset_class"] = {"literal": expected["asset_class"]}
            metadata_rules.setdefault("underlying", {"from_group": "underlying"})
            metadata_rules.setdefault("strike", {"from_group": "strike", "type": "float"})
            metadata_rules.setdefault("right", {"from_group": "right"})
            used_fields.add("symbol")

    for part in parts:
        if _is_boilerplate_part(part):
            continue
        matched = False
        upper_part = part.upper()

        # AVG$0.39 限价
        avg_m = re.fullmatch(r"AVG\$([\d.]+)", part, re.I)
        if avg_m and "limit_price" not in used_fields and (
            _float_eq(expected.get("limit_price"), avg_m.group(1))
            or expected.get("asset_class") == "OPTIONS"
        ):
            regex_parts.append(take_group("limit_price", r"AVG\$[\d.]+"))
            field_rules["limit_price"] = {
                "from_group": "limit_price",
                "type": "float",
                "strip_prefix": "AVG$",
            }
            if expected.get("order_type") == "LMT":
                field_rules["order_type"] = {"literal": "LMT"}
            used_fields.update({"limit_price", "order_type"})
            matched = True

        # @735.50 正股/期权限价（勿写成字面量，否则换价无法匹配）
        if not matched:
            at_m = re.fullmatch(r"@([\d.]+)", part)
            if at_m and "limit_price" not in used_fields and (
                _float_eq(expected.get("limit_price"), at_m.group(1))
                or expected.get("order_type") == "LMT"
            ):
                regex_parts.append(r"@" + take_group("limit_price", r"[\d.]+"))
                field_rules["limit_price"] = {"from_group": "limit_price", "type": "float"}
                if expected.get("order_type") == "LMT":
                    field_rules["order_type"] = {"literal": "LMT"}
                used_fields.update({"limit_price", "order_type"})
                matched = True

        # 10DTE
        if not matched:
            dte_m = re.fullmatch(r"(\d+)DTE", upper_part, re.I)
            if dte_m:
                regex_parts.append(take_group("dte", r"\d+DTE"))
                metadata_rules["dte"] = {
                    "from_group": "dte",
                    "type": "int",
                    "strip_suffix": "DTE",
                }
                matched = True

        # 2026-06-18 到期日
        if not matched and re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", part):
            regex_parts.append(take_group("expiry", r"\d{4}[-/]\d{2}[-/]\d{2}"))
            metadata_rules["expiry"] = {"from_group": "expiry"}
            matched = True

        # 单独 C / P（AVTR 10 C 格式）
        if not matched and re.fullmatch(r"[CP]", upper_part) and "right" not in group_map:
            exp_right = str(meta.get("right") or "").upper()
            sym_right = ""
            sym_m = re.search(r"(\d+)([CP])\b", str(expected.get("symbol", "")), re.I)
            if sym_m:
                sym_right = sym_m.group(2).upper()
            if upper_part == exp_right or upper_part == sym_right:
                regex_parts.append(take_group("right", r"[CP]"))
                metadata_rules["right"] = {"from_group": "right"}
                maybe_bind_option_symbol()
                matched = True

        # Numeric -> strike / limit_price / quantity
        if not matched and re.fullmatch(r"[\d.]+", part):
            num = float(part) if "." in part else int(part)
            if "strike" not in group_map and (
                (meta.get("strike") is not None and _float_eq(meta["strike"], num))
                or (
                    expected.get("asset_class") == "OPTIONS"
                    and "underlying" in group_map
                    and "right" in group_map
                )
            ):
                regex_parts.append(take_group("strike", r"[\d.]+"))
                metadata_rules["strike"] = {"from_group": "strike", "type": "float"}
                maybe_bind_option_symbol()
                matched = True
            elif "limit_price" not in used_fields and _float_eq(expected.get("limit_price"), num):
                regex_parts.append(take_group("limit_price", r"[\d.]+"))
                field_rules["limit_price"] = {"from_group": "limit_price", "type": "float"}
                if expected.get("order_type") == "LMT":
                    field_rules["order_type"] = {"literal": "LMT"}
                used_fields.update({"limit_price", "order_type"})
                matched = True
            elif "quantity" not in used_fields and expected.get("quantity") == num:
                regex_parts.append(take_group("quantity", r"\d+"))
                field_rules["quantity"] = {"from_group": "quantity", "type": "int"}
                used_fields.add("quantity")
                matched = True

        if not matched and "action" not in used_fields:
            action = str(expected.get("action", "")).upper()
            token = _find_token_for_action(part, action) or (
                upper_part if upper_part in ("BUY", "SELL", "ENTRY", "EXIT") else None
            )
            if token and token in upper_part:
                regex_parts.append(take_group("event", "ENTRY|EXIT|BUY|SELL"))
                field_rules["action"] = {
                    "from_group": "event",
                    "map": {"ENTRY": "BUY", "EXIT": "SELL", "BUY": "BUY", "SELL": "SELL"},
                }
                if expected.get("signal_subtype"):
                    field_rules["signal_subtype"] = {
                        "from_group": "event",
                        "map": {"ENTRY": "OPEN", "EXIT": "CLOSE", "BUY": "OPEN", "SELL": "CLOSE"},
                    }
                used_fields.add("action")
                matched = True

        if not matched and "symbol" not in used_fields:
            symbol = str(expected.get("symbol", ""))
            # SPY 758C style embedded in one token
            m = re.fullmatch(r"([A-Z][A-Z0-9]*)(\d+)([CP])", upper_part, re.I)
            if m and m.group(1) in symbol.upper():
                regex_parts.append(take_group("underlying", r"[A-Z][A-Z0-9]*"))
                regex_parts.append(take_group("strike", r"\d+"))
                regex_parts.append(take_group("right", r"[CP]"))
                field_rules["symbol"] = {"template": "{underlying} {strike}{right}"}
                if expected.get("asset_class"):
                    field_rules["asset_class"] = {"literal": expected["asset_class"]}
                metadata_rules.update(
                    {
                        "underlying": {"from_group": "underlying"},
                        "strike": {"from_group": "strike", "type": "int"},
                        "right": {"from_group": "right"},
                    }
                )
                used_fields.add("symbol")
                matched = True
            elif re.fullmatch(r"[A-Z][A-Z0-9]*", part, re.I) and (
                expected.get("asset_class") in ("OPTIONS", "STOCK")
                or (symbol and part.upper() in symbol.upper())
                or (meta.get("underlying") and part.upper() == str(meta["underlying"]).upper())
            ):
                if "underlying" not in group_map:
                    regex_parts.append(take_group("underlying", r"[A-Z][A-Z0-9]*"))
                    metadata_rules.setdefault("underlying", {"from_group": "underlying"})
                    if str(expected.get("asset_class") or "").upper() == "STOCK":
                        field_rules["symbol"] = {"from_group": "underlying"}
                        if expected.get("asset_class"):
                            field_rules["asset_class"] = {"literal": expected["asset_class"]}
                        used_fields.add("symbol")
                    else:
                        maybe_bind_option_symbol()
                    matched = True

        # $415K / $2.7M 等成交额提示：泛化 K/M/B 单位，避免样例写死导致其它消息匹配失败
        if not matched:
            prem_m = re.fullmatch(r"\$[\d.]+[KMB]", part, re.I)
            if prem_m:
                regex_parts.append(r"\$[\d.]+[KMB]")
                matched = True

        if not matched:
            if part.lower().startswith("signal"):
                regex_parts.append(_literal_to_regex(part.split("#")[0] + "#"))
                regex_parts.append(take_group("signal_ref", r"\d+"))
                metadata_rules["signal_ref"] = {"from_group": "signal_ref"}
            else:
                regex_parts.append(_literal_to_regex(part))

    maybe_bind_option_symbol()

    if not field_rules.get("action") and expected.get("action"):
        token = _find_token_for_action(sample, str(expected["action"]))
        if token:
            field_rules["action"] = {
                "from_group": "event",
                "map": {"ENTRY": "BUY", "EXIT": "SELL", "BUY": "BUY", "SELL": "SELL"},
            }
        else:
            field_rules["action"] = {"literal": str(expected["action"]).upper()}

    if not field_rules:
        return None

    if "quantity" not in field_rules and expected.get("quantity") is not None:
        field_rules["quantity"] = {"literal": expected["quantity"]}
    if "order_type" not in field_rules and expected.get("order_type"):
        field_rules["order_type"] = {"literal": expected["order_type"]}
    if "asset_class" not in field_rules and expected.get("asset_class"):
        field_rules["asset_class"] = {"literal": expected["asset_class"]}
    if "signal_subtype" not in field_rules and expected.get("signal_subtype"):
        token = _find_token_for_subtype(sample, str(expected["signal_subtype"]))
        if token:
            field_rules["signal_subtype"] = {
                "from_group": "event",
                "map": {"ENTRY": "OPEN", "EXIT": "CLOSE", "BUY": "OPEN", "SELL": "CLOSE"},
            }
        else:
            field_rules["signal_subtype"] = {"literal": str(expected["signal_subtype"]).upper()}

    pattern = r"\s*".join(regex_parts)
    return {
        "pattern": pattern,
        "groups": group_map,
        "field_rules": field_rules,
        "metadata_rules": metadata_rules,
    }


def generate_parse_rule_from_example(sample: str, expected_output: Dict[str, Any]) -> Dict[str, Any]:
    """根据输入样例与期望输出 JSON 生成 example 模式规则配置。"""
    sample = sample.strip()
    if not sample:
        raise ValueError("sample is required")

    normalized = _strip_boilerplate_lines(sample)
    config = _build_segment_pattern(normalized or sample, expected_output)
    if not config:
        raise ValueError("unable to infer parse rule from example; try adjusting output fields")

    # 若用户指定 symbol 模板，优先保留
    if expected_output.get("symbol") and "symbol" not in config.get("field_rules", {}):
        config.setdefault("field_rules", {})["symbol"] = {"literal": expected_output["symbol"]}

    return {
        "min_confidence": 0.5,
        **config,
        "example": {"sample": sample, "expected_output": expected_output},
    }


def summarize_generated_rule(config: Dict[str, Any]) -> str:
    """给人看的规则摘要。"""
    lines = [f"pattern: {config.get('pattern', '')}"]
    groups = config.get("groups") or {}
    if groups:
        lines.append("groups: " + ", ".join(f"{k}=#{v}" for k, v in groups.items()))
    field_rules = config.get("field_rules") or {}
    if field_rules:
        lines.append("fields: " + ", ".join(field_rules.keys()))
    return "\n".join(lines)
