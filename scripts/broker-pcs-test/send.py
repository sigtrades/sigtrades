#!/usr/bin/env python3
"""只发 SunnyQuant PCS Webhook 信号（不改路由；券商请在控制台手动切）。

用法:
  python3 scripts/broker-pcs-test/send.py
  python3 scripts/broker-pcs-test/send.py spy
  python3 scripts/broker-pcs-test/send.py spx
  python3 scripts/broker-pcs-test/send.py spy --token <WH_TOKEN>
  python3 scripts/broker-pcs-test/send.py spy --dry-run

配置: scripts/broker-pcs-test/config.json
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def next_friday(today: date | None = None) -> date:
    d = today or date.today()
    delta = (4 - d.weekday()) % 7
    return d if delta == 0 else d + timedelta(days=delta)


def round_strike(spot: float, step: float) -> float:
    return round(spot / step) * step


def occ_symbol(root: str, expiry: date, right: str, strike: float) -> str:
    return f"{root}{expiry.strftime('%y%m%d')}{right.upper()}{int(round(strike * 1000)):08d}"


def resolve_expiry(cfg: dict[str, Any], sym: dict[str, Any]) -> date:
    raw = sym.get("expiry") or cfg.get("expiry")
    if raw:
        return date.fromisoformat(str(raw)[:10])
    return next_friday()


def build_pcs_payload(cfg: dict[str, Any], symbol_key: str) -> dict[str, Any]:
    sym = cfg["symbols"][symbol_key]
    expiry = resolve_expiry(cfg, sym)
    short_strike = round_strike(float(sym["spot"]), float(sym["strike_step"]))
    width = float(sym["width"])
    long_strike = short_strike - width
    short_occ = occ_symbol(sym["root"], expiry, "P", short_strike)
    long_occ = occ_symbol(sym["root"], expiry, "P", long_strike)
    now = datetime.now(timezone.utc)
    signal_id = f"{sym['underlying']}_PCS_{now.strftime('%Y%m%d_%H%M%S')}"
    return {
        "contract_version": "sq_webhook_v2",
        "event": "structure_signal",
        "signal_id": signal_id,
        "timestamp": int(now.timestamp()),
        "strategy": "SQ-TGT",
        "strategy_family": "vertical_spread",
        "audience": "pcs_basic",
        "signal_subtype": "ENTRY",
        "signal_subtype_trade": "OPEN",
        "asset_class": sym["asset_class"],
        "direction": "down",
        "spx_price": float(sym["spot"]),
        "order": {
            "type": "ORDER",
            "action": "组合",
            "symbol": sym["underlying"],
            "quantity": int(cfg.get("default_quantity") or 1),
            "order_type": "LMT",
            "limit_price": float(sym["limit_price"]),
            "time_in_force": "DAY",
            "combo": "vertical_credit_spread",
            "limit_attempts": 1,
            "legs": [
                {"symbol": short_occ, "action": "SELL", "quantity": 1},
                {"symbol": long_occ, "action": "BUY", "quantity": 1},
            ],
        },
        "execution": {"leg_width": width},
        "source": "sunnyquant.broker_pcs_test",
    }


def post_webhook(cfg: dict[str, Any], wh_token: str, payload: dict[str, Any]) -> Any:
    url = f"{cfg['ingest_base'].rstrip('/')}/ingest/wh/{wh_token}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-SunnyQuant-Contract": "sq_webhook_v2",
        },
        method="POST",
    )
    # 本机 ingest 勿走系统代理（否则 localhost 常被 Clash 劫持成 502）
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"http_status": resp.status}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} POST {url}\n{detail}") from e


def print_curl(cfg: dict[str, Any], wh_token: str, payload: dict[str, Any]) -> None:
    url = f"{cfg['ingest_base'].rstrip('/')}/ingest/wh/{wh_token}"
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    print(f"curl -X POST '{url}' \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -H 'X-SunnyQuant-Contract: sq_webhook_v2' \\")
    print(f"  -d '{body}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="发送 PCS Webhook（不改路由）")
    parser.add_argument(
        "symbol",
        nargs="?",
        choices=["spy", "spx"],
        default=None,
        help="标的模板，默认读 config.default_symbol",
    )
    parser.add_argument("--token", help="覆盖 config.webhook_token")
    parser.add_argument("--dry-run", action="store_true", help="只打印 curl，不发送")
    args = parser.parse_args()

    cfg = load_config()
    symbol_key = (args.symbol or cfg.get("default_symbol") or "spy").lower()
    if symbol_key not in cfg["symbols"]:
        raise SystemExit(f"未知 symbol={symbol_key}，可选: {', '.join(cfg['symbols'])}")

    wh_token = (args.token or cfg.get("webhook_token") or "").strip()
    if not wh_token:
        raise SystemExit("请在 config.json 设置 webhook_token，或传 --token")

    payload = build_pcs_payload(cfg, symbol_key)
    print(f"[signal] {payload['signal_id']}")
    print(
        f"[legs]   {payload['order']['legs'][0]['symbol']} SELL / "
        f"{payload['order']['legs'][1]['symbol']} BUY  "
        f"LMT {payload['order']['limit_price']}"
    )
    print()
    print_curl(cfg, wh_token, payload)
    print()

    if args.dry_run:
        print("(dry-run，未发送)")
        return

    result = post_webhook(cfg, wh_token, payload)
    print("[ingest]", json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
