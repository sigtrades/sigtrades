#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send backup failure alert via Resend."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_backup_config(config_path: Path) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def send_failure_email(cfg: dict[str, Any], *, subject: str, body: str) -> None:
    alert = cfg.get("alert") or {}
    api_key = str(alert.get("resend_api_key") or "").strip()
    to_addr = str(alert.get("to") or "").strip()
    from_email = str(alert.get("from_email") or "").strip()
    from_name = str(alert.get("from_name") or "Backup").strip()
    if not api_key or not to_addr or not from_email:
        raise RuntimeError("alert.resend_api_key / to / from_email missing in pg_backup.json")

    payload = json.dumps(
        {
            "from": f"{from_name} <{from_email}>",
            "to": [to_addr],
            "subject": subject,
            "text": body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"Resend HTTP {resp.status}: {resp.read()[:300]!r}")
    except urllib.error.HTTPError as e:
        detail = e.read()[:500] if e.fp else b""
        raise RuntimeError(f"Resend HTTP {e.code}: {detail!r}") from e


if __name__ == "__main__":
    import argparse
    import sys

    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    args = p.parse_args()
    cfg = load_backup_config(Path(args.config))
    try:
        send_failure_email(cfg, subject=args.subject, body=args.body)
    except Exception as exc:
        print(f"notify failed: {exc}", file=sys.stderr)
        sys.exit(1)
