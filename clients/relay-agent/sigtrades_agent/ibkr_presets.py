"""IBKR 连接预设：与网页新增账号选项 / profile.account_id 对齐（仅 TWS）。"""

from __future__ import annotations

from typing import List, Tuple

# (account_id, display_name, port, client_id)
IBKR_PRESETS: List[Tuple[str, str, int, int]] = [
    ("tws-paper", "7497 · TWS 模拟", 7497, 1),
    ("tws-live", "7496 · TWS 实盘", 7496, 2),
]
