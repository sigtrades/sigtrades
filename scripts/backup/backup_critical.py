#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pull critical Postgres tables from HK → local backup_root (mac-mini).

Flow: remote per-table pg_dump → gzip on HK → scp → delete remote temp.
Does not run on deploy. Cron only on the backup host, e.g.:
  5 8 * * * /usr/bin/env TZ=Asia/Shanghai python3 .../backup_critical.py
"""

from __future__ import annotations

import gzip
import os
import subprocess
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "pg_backup.json"

sys.path.insert(0, str(SCRIPT_DIR))
from notify_failure import load_backup_config, send_failure_email  # noqa: E402


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%F %T')}] {msg}", flush=True)


def _acquire_lock(lock_dir: Path) -> None:
    try:
        lock_dir.mkdir(mode=0o700)
    except FileExistsError as e:
        raise RuntimeError(f"another backup is running ({lock_dir})") from e


def _release_lock(lock_dir: Path) -> None:
    try:
        lock_dir.rmdir()
    except OSError:
        pass


def _ssh_base(cfg: dict[str, Any]) -> list[str]:
    hk = cfg["hk"]
    return [
        "ssh",
        "-i",
        str(hk["pem"]),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={int(hk.get('connect_timeout_sec') or 20)}",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=4",
        str(hk["ssh_host"]),
    ]


def _scp_base(cfg: dict[str, Any]) -> list[str]:
    hk = cfg["hk"]
    return [
        "scp",
        "-i",
        str(hk["pem"]),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={int(hk.get('connect_timeout_sec') or 20)}",
    ]


def _run(cmd: list[str], *, what: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:2000]
        out = (proc.stdout or b"").decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{what} failed rc={proc.returncode}: {err or out}")
    return proc


def _dump_remote_to_gz(cfg: dict[str, Any], remote_gz: str) -> None:
    db = cfg["database"]
    tables: list[str] = list(db["tables"])
    if not tables:
        raise RuntimeError("database.tables is empty")
    dump_mode = str(db.get("dump_mode") or "data-only").strip().lower()
    mode_flag = "--data-only" if dump_mode == "data-only" else ""
    for t in tables:
        if not t.replace("_", "").isalnum():
            raise RuntimeError(f"invalid table name: {t!r}")
    table_list = " ".join(tables)
    remote_sql = remote_gz[: -3] if remote_gz.endswith(".gz") else remote_gz + ".sql"
    remote = f"""set -euo pipefail
rm -f '{remote_sql}' '{remote_gz}'
: > '{remote_sql}'
for t in {table_list}; do
  sudo -n docker exec {db["container"]} \
    pg_dump -U {db["user"]} -d {db["db"]} --no-owner --no-acl {mode_flag} -t "$t" >> '{remote_sql}'
done
gzip -f '{remote_sql}'
test -s '{remote_gz}'
ls -la '{remote_gz}'
"""
    _log(f"remote dump {db['container']}/{db['db']} tables={len(tables)} mode={dump_mode}")
    _run(_ssh_base(cfg) + [remote], what="remote pg_dump")


def _fetch_and_cleanup(cfg: dict[str, Any], remote_gz: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = local_path.with_suffix(local_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    host = str(cfg["hk"]["ssh_host"])
    _log(f"scp {remote_gz} → {tmp}")
    _run(_scp_base(cfg) + [f"{host}:{remote_gz}", str(tmp)], what="scp")
    with gzip.open(tmp, "rb") as f:
        while f.read(1024 * 1024):
            pass
    if tmp.stat().st_size < 32:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("downloaded gzip too small")
    tmp.replace(local_path)
    _run(_ssh_base(cfg) + [f"rm -f '{remote_gz}'"], what="remote cleanup")


def _prune(backup_root: Path, product: str, keep: int) -> None:
    files = sorted(
        backup_root.glob(f"{product}_critical_*.sql.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[keep:]:
        old.unlink(missing_ok=True)
        _log(f"prune {old}")


def run(config_path: Path) -> Path:
    cfg = load_backup_config(config_path)
    product = str(cfg.get("product") or "db")
    backup_root = Path(cfg["backup_root"])
    keep = int(cfg.get("keep") or 3)
    lock_dir = Path(cfg.get("lock_dir") or f"/tmp/{product}_pg_backup.lock")
    tz_name = str(cfg.get("schedule_tz") or "Asia/Shanghai")
    now = datetime.now(ZoneInfo(tz_name))
    stamp = now.strftime("%Y%m%d_%H%M%S")
    out = backup_root / f"{product}_critical_{stamp}.sql.gz"
    remote_gz = f"/tmp/{product}_critical_{stamp}_{uuid.uuid4().hex[:8]}.sql.gz"

    _acquire_lock(lock_dir)
    try:
        try:
            _dump_remote_to_gz(cfg, remote_gz)
            _fetch_and_cleanup(cfg, remote_gz, out)
        except Exception:
            try:
                subprocess.run(
                    _ssh_base(cfg) + [f"rm -f '{remote_gz}' '{remote_gz[:-3]}'"],
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                pass
            raise
        _prune(backup_root, product, keep)
        _log(f"OK {out} ({out.stat().st_size} bytes)")
        return out
    finally:
        _release_lock(lock_dir)


def main() -> int:
    config_path = Path(os.environ.get("PG_BACKUP_CONFIG") or DEFAULT_CONFIG)
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    if not config_path.is_file():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 2

    cfg: dict[str, Any] = {}
    try:
        cfg = load_backup_config(config_path)
        run(config_path)
        return 0
    except Exception as exc:
        _log(f"FAILED: {exc}")
        tb = traceback.format_exc()
        product = str((cfg or {}).get("product") or "backup")
        day = datetime.now().strftime("%Y-%m-%d")
        subject = f"[{product} backup FAILED] {day}"
        body = (
            f"product: {product}\n"
            f"config: {config_path}\n"
            f"host: {os.uname().nodename}\n"
            f"error: {exc}\n\n"
            f"{tb}\n"
        )
        try:
            if not cfg:
                cfg = load_backup_config(config_path)
            send_failure_email(cfg, subject=subject, body=body)
            _log(f"alert mailed to {(cfg.get('alert') or {}).get('to')}")
        except Exception as mail_exc:
            _log(f"alert email failed: {mail_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
