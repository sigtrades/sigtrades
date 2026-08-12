#!/usr/bin/env python3
"""本机探测 TWS：TCP + ib_async API 握手。

用法:
  python3 scripts/probe_ibkr_gateway.py
  python3 scripts/probe_ibkr_gateway.py --port 7497 --client-id 97
  python3 scripts/probe_ibkr_gateway.py --host 127.0.0.1 --port 7496
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import sys
import time


def tcp_probe(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP OK {host}:{port}"
    except OSError as exc:
        return False, f"TCP FAIL {host}:{port} — {exc}"


def api_probe(host: str, port: int, client_id: int, timeout: float) -> tuple[bool, str]:
    try:
        from ib_async import IB
    except ImportError:
        return False, "未安装 ib_async，请先: pip install ib_async"

    # ib_async 需要事件循环
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    ib = IB()
    t0 = time.monotonic()
    try:
        ib.connect(
            host=host,
            port=port,
            clientId=client_id,
            timeout=timeout,
            readonly=True,
        )
        elapsed = time.monotonic() - t0
        accounts = list(ib.managedAccounts() or [])
        summary_rows = []
        try:
            # 只读拉一点账户摘要，确认不只是空连接
            for av in ib.accountSummary() or []:
                if av.tag in {"NetLiquidation", "TotalCashValue", "BuyingPower"}:
                    summary_rows.append(f"{av.tag}={av.value} {av.currency}".strip())
                if len(summary_rows) >= 6:
                    break
        except Exception as exc:  # noqa: BLE001
            summary_rows.append(f"(accountSummary 失败: {exc})")

        server = getattr(ib.client, "serverVersion", lambda: "?")()
        msg = (
            f"API OK in {elapsed:.1f}s | serverVersion={server} | "
            f"accounts={accounts or ['(empty)']}"
        )
        if summary_rows:
            msg += "\n  " + "\n  ".join(summary_rows)
        return True, msg
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        tip = ""
        err = str(exc).lower()
        if "timeout" in err or "timed out" in err:
            tip = (
                "\n  提示: TCP 通但 API 超时常见原因 — "
                "TWS 弹窗未点 Accept；API 未启用；"
                "clientId 冲突；系统/Clash 代理干扰。"
            )
        elif "already in use" in err or "duplicate" in err:
            tip = "\n  提示: clientId 已被占用，换一个 --client-id 再试。"
        return False, f"API FAIL after {elapsed:.1f}s — {type(exc).__name__}: {exc}{tip}"
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    p = argparse.ArgumentParser(description="Probe TWS API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7497, help="7497=TWS paper, 7496=TWS live")
    p.add_argument("--client-id", type=int, default=97, help="避免与 Agent 默认 clientId 冲突")
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args()

    print(f"== IBKR probe {args.host}:{args.port} clientId={args.client_id} ==")
    ok_tcp, tcp_msg = tcp_probe(args.host, args.port, min(args.timeout, 3.0))
    print(f"[1/2] {tcp_msg}")
    if not ok_tcp:
        print("结论: 端口不可达 — 请先启动 TWS 并打开 Socket API。")
        return 2

    ok_api, api_msg = api_probe(args.host, args.port, args.client_id, args.timeout)
    print(f"[2/2] {api_msg}")
    if ok_api:
        print("结论: TWS API 握手成功。")
        return 0
    print("结论: TWS API 握手失败。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
