"""产品图标路径（开发 / PyInstaller 打包）。"""

from __future__ import annotations

import sys
from pathlib import Path


def logo_png() -> Path | None:
    """返回可用的 logo.png（优先打包资源，其次 UI public/dist）。"""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        candidates.extend(
            [
                exe_dir / "icons" / "logo.png",
                exe_dir / "_internal" / "icons" / "logo.png",
                meipass / "icons" / "logo.png",
                exe_dir / "ui" / "logo.png",
                exe_dir / "_internal" / "ui" / "logo.png",
                meipass / "ui" / "logo.png",
            ]
        )
    root = Path(__file__).resolve().parents[1]
    # 优先 macOS squircle 成品，再回退方图
    candidates.extend(
        [
            root / "build" / "icons" / "sigtrades-agent-mac.png",
            root / "build" / "icons" / "sigtrades-agent-256.png",
            root / "build" / "icons" / "logo.png",
            root / "ui" / "public" / "logo.png",
            root / "ui" / "dist" / "logo.png",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None
