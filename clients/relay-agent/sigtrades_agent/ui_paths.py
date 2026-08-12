"""Agent 内置 React UI 静态资源路径（开发 / PyInstaller 打包）。"""

from __future__ import annotations

import sys
from pathlib import Path


def ui_dist_dir() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "ui",
            exe_dir / "_internal" / "ui",
            Path(getattr(sys, "_MEIPASS", exe_dir)) / "ui",
        ])
    root = Path(__file__).resolve().parents[1]
    candidates.append(root / "ui" / "dist")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return None
