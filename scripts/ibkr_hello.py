#!/usr/bin/env python3
"""最小 TWS 连通测试（不依赖 Agent）。

  pip install ib_async
  python3 scripts/ibkr_hello.py
  python3 scripts/ibkr_hello.py --port 7497 --client-id 999
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import sys


def tcp_ok(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError as exc:
        print(f"[1/2] TCP FAIL {host}:{port} — {exc}")
        return False


async def api_ok(host: str, port: int, client_id: int, timeout: float) -> bool:
    from ib_async import IB

    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=timeout, readonly=True)
        print(f"[2/2] API OK  accounts={ib.managedAccounts()}")
        ib.disconnect()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[2/2] API FAIL — {type(exc).__name__}: {exc}")
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7497)
    p.add_argument("--client-id", type=int, default=999)
    p.add_argument("--timeout", type=float, default=10.0)
    args = p.parse_args()

    print(f"hello IBKR {args.host}:{args.port} clientId={args.client_id}")
    if not tcp_ok(args.host, args.port):
        print("结论: 端口不可达 — 请启动 TWS 并打开 Socket API。")
        return 2
    print(f"[1/2] TCP OK {args.host}:{args.port}")
    ok = asyncio.run(api_ok(args.host, args.port, args.client_id, args.timeout))
    if ok:
        print("结论: 握手成功。")
        return 0
    print("结论: API 握手失败 — 可 Force Quit TWS 后重开再试。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
