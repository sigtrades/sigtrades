"""富途连接预设：与网页新增账号选项 / profile.account_id 对齐。"""

from __future__ import annotations

from typing import List, Tuple

# (account_id, display_name, trd_env, port)
FUTU_PRESETS: List[Tuple[str, str, str, int]] = [
    ("futu-simulate", "SIMULATE · 模拟", "SIMULATE", 11111),
    ("futu-real", "REAL · 实盘", "REAL", 11111),
]
