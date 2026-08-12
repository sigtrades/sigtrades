"""Agent 本地 SQLite 幂等存储。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from sigtrades_agent.config import default_config_dir


def db_path() -> Path:
    return default_config_dir() / "idem.db"


def _conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS idem (
            source_id TEXT NOT NULL,
            signal_id TEXT NOT NULL,
            account_id TEXT,
            status TEXT NOT NULL,
            payload TEXT,
            PRIMARY KEY (source_id, signal_id, account_id)
        )
        """
    )
    return conn


def get_terminal(source_id: str, signal_id: str, account_id: Optional[str]) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT payload FROM idem WHERE source_id=? AND signal_id=? AND account_id IS ?",
            (source_id, signal_id, account_id),
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def save_terminal(source_id: str, signal_id: str, account_id: Optional[str], payload: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO idem (source_id, signal_id, account_id, status, payload) VALUES (?,?,?,?,?)",
            (source_id, signal_id, account_id, payload.get("status", ""), json.dumps(payload)),
        )


def get_stats() -> dict:
    """本机累计处理统计（来自幂等库）。"""
    with _conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM idem GROUP BY status").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM idem").fetchone()
    by_status = {status: count for status, count in rows}
    filled = sum(by_status.get(s, 0) for s in ("FILLED", "PARTIAL"))
    failed = sum(by_status.get(s, 0) for s in ("FAILED", "REJECTED", "ERROR"))
    return {
        "total_processed": int(total[0] if total else 0),
        "filled": filled,
        "failed": failed,
        "by_status": by_status,
    }
