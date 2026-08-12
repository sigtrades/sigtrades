"""信号解析：结构化 / 正则 / 示例规则 / AI（可选 LLM）。"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sigtrades_core.parse.rule_generator import signal_hash_option_config
from sigtrades_core.signal.option_symbol import apply_source_option_dte


@dataclass
class ParseResult:
    signal: Dict[str, Any]
    confidence: float
    mode: str
    error: Optional[str] = None
    matched_label: Optional[str] = None


def _base_signal(raw_text: str = "") -> Dict[str, Any]:
    return {
        "signal_id": f"parse-{uuid.uuid4().hex[:12]}",
        "timestamp": time.time(),
        "type": "ORDER",
        "action": "",
        "symbol": "",
        "quantity": 0,
        "order_type": "MKT",
        "metadata": {"raw_text": raw_text},
    }


def parse_structured(payload: Dict[str, Any], mapping: Optional[Dict[str, str]] = None) -> ParseResult:
    """已知 JSON 字段直映射。"""
    mapping = mapping or {}
    field_map = {
        "action": mapping.get("action", "action"),
        "symbol": mapping.get("symbol", "symbol"),
        "quantity": mapping.get("quantity", "quantity"),
        "limit_price": mapping.get("limit_price", "limit_price"),
        "order_type": mapping.get("order_type", "order_type"),
    }
    sig = _base_signal(json.dumps(payload, ensure_ascii=False))
    for target, source_key in field_map.items():
        val = payload.get(source_key)
        if val is None and source_key == "symbol":
            val = payload.get("ticker")
        if val is not None:
            sig[target] = val
    if not sig.get("symbol") and payload.get("ticker"):
        sig["symbol"] = payload["ticker"]
    if not sig.get("action") and payload.get("side"):
        sig["action"] = str(payload["side"]).upper()
    confidence = 1.0 if sig.get("action") and sig.get("symbol") else 0.3
    return ParseResult(signal=sig, confidence=confidence, mode="structured")


def _coerce_value(raw: str, typ: str, rule: Optional[Dict[str, Any]] = None) -> Any:
    val = raw
    if rule:
        prefix = rule.get("strip_prefix")
        if prefix and val.upper().startswith(str(prefix).upper()):
            val = val[len(str(prefix)) :]
        suffix = rule.get("strip_suffix")
        if suffix and val.upper().endswith(str(suffix).upper()):
            val = val[: -len(str(suffix))]
    if typ == "int":
        return int(float(val))
    if typ == "float":
        return float(val)
    return val


def _capture_groups(match: re.Match[str], groups: Dict[str, int]) -> Dict[str, str]:
    captured: Dict[str, str] = {}
    for name, idx in groups.items():
        try:
            captured[name] = match.group(idx)
        except IndexError:
            pass
    return captured


def _apply_field_rules(
    sig: Dict[str, Any],
    captured: Dict[str, str],
    field_rules: Dict[str, Any],
    metadata_rules: Optional[Dict[str, Any]] = None,
) -> None:
    for field, rule in field_rules.items():
        if "literal" in rule:
            sig[field] = rule["literal"]
            continue
        if "from_group" in rule:
            raw = captured.get(rule["from_group"])
            if raw is None:
                continue
            if "map" in rule:
                sig[field] = rule["map"].get(raw.upper(), rule["map"].get(raw, raw))
            else:
                sig[field] = _coerce_value(raw, rule.get("type", "str"), rule)
            if field == "action" and isinstance(sig[field], str):
                sig[field] = sig[field].upper()
            continue
        if "template" in rule:
            try:
                sig[field] = rule["template"].format(**captured)
            except KeyError:
                pass


def _apply_metadata_rules(
    sig: Dict[str, Any],
    captured: Dict[str, str],
    metadata_rules: Dict[str, Any],
) -> None:
    meta = dict(sig.get("metadata") or {})
    for field, rule in metadata_rules.items():
        if "from_group" not in rule:
            continue
        raw = captured.get(rule["from_group"])
        if raw is None:
            continue
        meta[field] = _coerce_value(raw, rule.get("type", "str"), rule)
    sig["metadata"] = meta


def parse_with_rule_config(
    text: str,
    config: Dict[str, Any],
    *,
    mode_label: str = "regex",
) -> ParseResult:
    """按 pattern + field_rules 解析（regex / example 共用）。"""
    sig = _base_signal(text)
    pattern = config.get("pattern", "")
    field_rules = config.get("field_rules")
    try:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    except re.error as e:
        return ParseResult(signal=sig, confidence=0.0, mode=mode_label, error=str(e))
    if not m:
        return ParseResult(signal=sig, confidence=0.0, mode=mode_label, error="no match")

    if field_rules:
        groups = config.get("groups") or {}
        captured = _capture_groups(m, groups)
        _apply_field_rules(sig, captured, field_rules, config.get("metadata_rules"))
        if config.get("metadata_rules"):
            _apply_metadata_rules(sig, captured, config["metadata_rules"])
    else:
        groups = config.get("groups") or {"symbol": 1, "action": 2, "quantity": 3}
        for field, idx in groups.items():
            try:
                val = m.group(idx)
                if field == "quantity":
                    sig[field] = int(float(val))
                elif field == "limit_price":
                    sig[field] = float(val)
                    sig["order_type"] = "LMT"
                else:
                    sig[field] = val.upper() if field == "action" else val
            except (IndexError, ValueError):
                pass

    if sig.get("limit_price") and not sig.get("order_type"):
        sig["order_type"] = "LMT"
    # 期权结构化字段同步进 metadata，供执行层 option_symbol 适配器使用
    meta = dict(sig.get("metadata") or {})
    for key in ("underlying", "strike", "right"):
        if sig.get(key) is not None and meta.get(key) is None:
            meta[key] = sig[key]
    if meta:
        sig["metadata"] = meta
    sig = sanitize_stock_vs_option(sig)
    confidence = 0.95 if sig.get("action") and sig.get("symbol") else 0.4
    return ParseResult(signal=sig, confidence=confidence, mode=mode_label)


def parse_regex(text: str, pattern: str, groups: Optional[Dict[str, int]] = None) -> ParseResult:
    """用户自定义正则抽取字段。groups 例：{"symbol": 1, "action": 2}。"""
    config: Dict[str, Any] = {"pattern": pattern, "groups": groups or {"symbol": 1, "action": 2, "quantity": 3}}
    return parse_with_rule_config(text, config, mode_label="regex")


def parse_example(text: str, config: Dict[str, Any]) -> ParseResult:
    """样例驱动规则（自动生成 pattern + field_rules）。"""
    return parse_with_rule_config(text, config, mode_label="example")


def parse_signal_hash_option(text: str) -> Optional[ParseResult]:
    """内置期权格式：Signal#173-SPY-758C-ENTRY-0.93"""
    config = signal_hash_option_config()
    result = parse_with_rule_config(text, config, mode_label="signal_hash")
    if result.error:
        return None
    return result


def parse_heuristic(text: str) -> ParseResult:
    """无 LLM 时的轻量启发式（英/中常见喊单）。"""
    option_hit = parse_signal_hash_option(text)
    if option_hit and option_hit.confidence >= 0.5:
        return option_hit

    sig = _base_signal(text)
    upper = text.upper()
    for word in ("BUY", "SELL", "买入", "卖出", "做多", "做空"):
        if word in text or word in upper:
            sig["action"] = "BUY" if word in ("BUY", "买入", "做多") else "SELL"
            break
    skip = {"BUY", "SELL", "CALL", "PUT", "LONG", "SHORT"}
    for m in re.finditer(r"\b([A-Z]{2,5})\b", upper):
        if m.group(1) not in skip:
            sig["symbol"] = m.group(1)
            sig["asset_class"] = "STOCK"
            break
    qty = re.search(r"(?:qty|quantity|数量|张数)[:\s]*(\d+)", text, re.I)
    if qty:
        sig["quantity"] = int(qty.group(1))
    elif sig.get("action"):
        sig["quantity"] = 1
    price = re.search(r"(?:@|at|价格|限价)[:\s]*\$?([\d.]+)", text, re.I)
    if price:
        sig["limit_price"] = float(price.group(1))
        sig["order_type"] = "LMT"
    # BUY SPY 100 @735.50 → 数量在 ticker 与 @ 之间
    stock_qty = re.search(
        r"\b(?:BUY|SELL)\s+([A-Z]{1,6})\s+(\d+)\s*@",
        text,
        re.I,
    )
    if stock_qty and sig.get("asset_class") == "STOCK":
        sig["symbol"] = stock_qty.group(1).upper()
        sig["quantity"] = int(stock_qty.group(2))
    sig = sanitize_stock_vs_option(sig)
    confidence = 0.7 if sig.get("action") and sig.get("symbol") else 0.2
    return ParseResult(signal=sig, confidence=confidence, mode="heuristic")


_OPTION_SYM_RE = re.compile(
    r"^([A-Z][A-Z0-9.]*)\s+(\d+(?:\.\d+)?)([CP])$",
    re.I,
)
_OPTION_COMPACT_RE = re.compile(
    r"^([A-Z][A-Z0-9.]*)(\d+(?:\.\d+)?)([CP])$",
    re.I,
)


def _underlying_from_symbol(symbol: str) -> str:
    text = (symbol or "").strip().upper()
    if not text:
        return ""
    m = _OPTION_SYM_RE.match(text) or _OPTION_COMPACT_RE.match(text)
    if m:
        return m.group(1).upper()
    return text.split()[0]


def _strike_from_signal(sig: Dict[str, Any]) -> Optional[float]:
    meta = sig.get("metadata") if isinstance(sig.get("metadata"), dict) else {}
    if meta.get("strike") is not None:
        try:
            return float(meta["strike"])
        except (TypeError, ValueError):
            pass
    sym = str(sig.get("symbol") or "").strip().upper()
    m = _OPTION_SYM_RE.match(sym) or _OPTION_COMPACT_RE.match(sym)
    if m:
        try:
            return float(m.group(2))
        except (TypeError, ValueError):
            return None
    return None


def sanitize_stock_vs_option(sig: Dict[str, Any]) -> Dict[str, Any]:
    """纠正正股被误标为期权（常见：把 @现价 当成行权价）。

    例：``BUY SPY 100 @735.50`` 被解析成 ``SPY 735C`` / OPTIONS → 老虎走期权链报合约不正确。
    """
    if not isinstance(sig, dict):
        return sig
    ac = str(sig.get("asset_class") or "").upper()
    sym = str(sig.get("symbol") or "").strip()
    meta = dict(sig.get("metadata") or {}) if isinstance(sig.get("metadata"), dict) else {}

    if ac == "STOCK":
        # 正股不应残留期权腿/行权字段
        for k in ("strike", "right", "option_type", "expiry", "expiry_date", "dte"):
            meta.pop(k, None)
        sig["metadata"] = meta
        return sig

    # 纯 ticker、无 strike/right → STOCK
    if sym and " " not in sym and re.fullmatch(r"[A-Z][A-Z0-9.]*", sym.upper()):
        if not re.search(r"\d+[CP]$", sym.upper()) and not (
            meta.get("strike") is not None and meta.get("right")
        ):
            sig["asset_class"] = "STOCK"
            return sig

    # 限价≈行权价（且限价偏高，像正股价而非权利金）→ 正股误判
    px = sig.get("limit_price")
    strike = _strike_from_signal(sig)
    try:
        px_f = float(px) if px is not None else None
    except (TypeError, ValueError):
        px_f = None
    if (
        px_f is not None
        and strike is not None
        and px_f >= 20
        and abs(px_f - strike) <= max(1.0, 0.05 * px_f)
    ):
        und = str(meta.get("underlying") or _underlying_from_symbol(sym) or "").upper()
        if und:
            sig["symbol"] = und
            sig["asset_class"] = "STOCK"
            for k in ("strike", "right", "option_type", "expiry", "expiry_date", "dte"):
                meta.pop(k, None)
            if und and "underlying" not in meta:
                meta["underlying"] = und
            sig["metadata"] = meta
            # 正股数量：若 AI 把 qty 丢掉只留 1，尽量从原文恢复
            raw = str(meta.get("raw_text") or "")
            qty_m = re.search(
                rf"\b{re.escape(und)}\s+(\d+(?:\.\d+)?)\s*@",
                raw,
                re.I,
            )
            if qty_m:
                try:
                    q = float(qty_m.group(1))
                    if q >= 1 and abs(q - strike) > 1e-6:
                        sig["quantity"] = int(q) if q == int(q) else q
                except (TypeError, ValueError):
                    pass
    return sig


def _extract_json_object(content: str) -> Dict[str, Any]:
    """从模型输出中取出 JSON 对象（兼容 markdown fence / 前后废话）。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("empty AI content")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        data = json.loads(fence.group(1).strip())
        if isinstance(data, dict):
            return data
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError(f"AI content is not JSON: {text[:200]}")


async def parse_ai(
    text: str,
    prompt: Optional[str] = None,
    api_key: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 2000,
    timeout: float = 30.0,
) -> ParseResult:
    """LLM 解析；无 key 时降级启发式。base_url 须含 /v1（OpenAI-compat）。

    注意：部分 OpenAI-compat 网关（如 packyapi 的 gpt-5.5）不支持 chat completions，
    或拒绝 response_format；此处不发送 response_format，并在提示词中要求纯 JSON。
    """
    if not api_key:
        r = parse_heuristic(text)
        r.mode = "ai_fallback"
        return r
    try:
        import httpx

        system = prompt or (
            "Extract trading signal as JSON only (no markdown): "
            "action(BUY/SELL), symbol, quantity(int), limit_price(float|null), "
            "order_type(LMT|MKT), signal_subtype(OPEN/CLOSE|null), "
            "asset_class(STOCK/OPTIONS). "
            "STOCK vs OPTIONS: "
            "'BUY SPY 100 @735.50' is STOCK (ticker + share qty + stock price) — "
            "symbol=SPY, quantity=100, limit_price=735.50, asset_class=STOCK. "
            "'BUY SPY 735C @2.45' is OPTIONS (ticker + strike+C/P + premium) — "
            "symbol='SPY 735C', quantity=1, limit_price=2.45, asset_class=OPTIONS. "
            "Never treat a stock @price as an option strike. "
            "For Signal#173-SPY-758C-ENTRY-0.93: ENTRY=BUY/OPEN, 758C=strike+right. "
            "Language-agnostic. Return a single JSON object."
        )
        root = (base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{root}/chat/completions"
        payload = {
            "model": (model or "gpt-5.4").strip() or "gpt-5.4",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "max_tokens": max(256, min(int(max_tokens or 2000), 20000)),
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code >= 400:
            detail = resp.text
            try:
                err = resp.json().get("error") or {}
                detail = err.get("message") or detail
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"AI HTTP {resp.status_code}: {detail}")
        content = resp.json()["choices"][0]["message"]["content"]
        data = _extract_json_object(content)
        sig = _base_signal(text)
        for k in ("action", "symbol", "quantity", "limit_price", "order_type", "signal_subtype", "asset_class"):
            if k in data and data[k] is not None:
                sig[k] = data[k]
        if sig.get("action"):
            sig["action"] = str(sig["action"]).upper()
        if sig.get("order_type"):
            sig["order_type"] = str(sig["order_type"]).upper()
        if sig.get("signal_subtype"):
            sig["signal_subtype"] = str(sig["signal_subtype"]).upper()
        if sig.get("asset_class"):
            sig["asset_class"] = str(sig["asset_class"]).upper()
        if sig.get("limit_price") and not sig.get("order_type"):
            sig["order_type"] = "LMT"
        if isinstance(sig.get("metadata"), dict) and not sig["metadata"].get("raw_text"):
            sig["metadata"]["raw_text"] = text
        sig = sanitize_stock_vs_option(sig)
        confidence = float(data.get("confidence", 0.85))
        return ParseResult(signal=sig, confidence=confidence, mode="ai")
    except Exception as e:  # noqa: BLE001
        r = parse_heuristic(text)
        r.mode = "ai_fallback"
        r.error = str(e)
        return r


def _normalize_parse_input(raw: Any) -> tuple[str, Optional[str], Any]:
    """提取正文、发送者与结构化解析载荷。"""
    author: Optional[str] = None
    if isinstance(raw, dict):
        author = raw.get("author")
        if not author:
            meta = raw.get("metadata") or {}
            if isinstance(meta, dict):
                author = meta.get("author")
        if raw.get("raw_text") is not None:
            return str(raw["raw_text"]), str(author) if author else None, raw
        return json.dumps(raw, ensure_ascii=False), str(author) if author else None, raw
    return str(raw), None, raw


def _author_matches(config: Dict[str, Any], author: Optional[str]) -> bool:
    if not config.get("author_filter"):
        return True
    allowed = str(config.get("allowed_author") or "").strip()
    if not allowed or not author:
        return False
    a = author.strip().lower()
    b = allowed.strip().lower()
    return a == b


def _rule_applicable(config: Dict[str, Any], author: Optional[str]) -> bool:
    if not config.get("author_filter"):
        return True
    return _author_matches(config, author)


def _dte_from_rule_config(config: Dict[str, Any]) -> Optional[int]:
    if config.get("option_default_dte") is not None:
        try:
            return int(config["option_default_dte"])
        except (TypeError, ValueError):
            pass
    ex = config.get("example")
    if isinstance(ex, dict):
        expected = ex.get("expected_output")
        if isinstance(expected, dict):
            meta = expected.get("metadata")
            if isinstance(meta, dict) and meta.get("dte") is not None:
                try:
                    return int(meta["dte"])
                except (TypeError, ValueError):
                    pass
    return None


def _finalize_parse_result(result: ParseResult, option_default_dte: Optional[int]) -> ParseResult:
    if result.error:
        return result
    result.signal = sanitize_stock_vs_option(result.signal)
    if option_default_dte is None:
        return result
    meta = result.signal.get("metadata") or {}
    if meta.get("expiry") or meta.get("expiry_date"):
        return result
    result.signal = apply_source_option_dte(result.signal, option_default_dte)
    return result


async def apply_parse_rules(
    raw: Any,
    rules: List[Dict[str, Any]],
    *,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
    openai_model: Optional[str] = None,
    openai_max_tokens: int = 2000,
    openai_timeout: float = 30.0,
    allow_ai: bool = True,
    option_default_dte: Optional[int] = None,
) -> ParseResult:
    """按优先级尝试多条规则，命中即返回。"""
    text, author, parse_payload = _normalize_parse_input(raw)

    sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
    applicable = [
        r for r in sorted_rules
        if _rule_applicable(r.get("config") or {}, author)
    ]
    if sorted_rules and not applicable:
        sig = _base_signal(text)
        return _finalize_parse_result(
            ParseResult(signal=sig, confidence=0.0, mode="skipped", error="author_filter"),
            option_default_dte,
        )

    for rule in applicable:
        mode = rule.get("parse_mode") or rule.get("mode", "heuristic")
        config = rule.get("config") or {}
        label = rule.get("label")
        if mode == "structured" and isinstance(parse_payload, dict):
            result = parse_structured(parse_payload, config.get("mapping"))
            rule_dte = _dte_from_rule_config(config)
            effective_dte = rule_dte if rule_dte is not None else option_default_dte
            if result.confidence >= float(config.get("min_confidence", 0.5)):
                result.matched_label = label
                return _finalize_parse_result(result, effective_dte)
        elif mode == "regex":
            if config.get("field_rules"):
                result = parse_with_rule_config(text, config, mode_label="regex")
            else:
                result = parse_regex(text, config.get("pattern", ""), config.get("groups"))
            rule_dte = _dte_from_rule_config(config)
            effective_dte = rule_dte if rule_dte is not None else option_default_dte
            if result.confidence >= float(config.get("min_confidence", 0.5)):
                result.matched_label = label
                return _finalize_parse_result(result, effective_dte)
        elif mode == "example":
            result = parse_example(text, config)
            rule_dte = _dte_from_rule_config(config)
            effective_dte = rule_dte if rule_dte is not None else option_default_dte
            if result.confidence >= float(config.get("min_confidence", 0.5)):
                result.matched_label = label
                return _finalize_parse_result(result, effective_dte)
        elif mode == "ai":
            if not allow_ai:
                continue
            result = await parse_ai(
                text,
                config.get("prompt"),
                openai_api_key,
                base_url=openai_base_url,
                model=openai_model,
                max_tokens=openai_max_tokens,
                timeout=openai_timeout,
            )
            rule_dte = _dte_from_rule_config(config)
            effective_dte = rule_dte if rule_dte is not None else option_default_dte
            if result.confidence >= float(config.get("min_confidence", 0.5)):
                result.matched_label = label
                return _finalize_parse_result(result, effective_dte)
    return _finalize_parse_result(parse_heuristic(text), option_default_dte)
