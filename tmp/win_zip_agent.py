"""Zip built Windows agent dist into data/agent-releases."""
from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path

ROOT = Path(r"E:/work/sigtrades")
SRC = ROOT / "clients/relay-agent/dist/sigtrades-agent"
RELEASES = ROOT / "data/agent-releases"
init_text = (ROOT / "clients/relay-agent/sigtrades_agent/__init__.py").read_text(encoding="utf-8")
import re

m = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
VERSION = m.group(1) if m else "0.1.9"
OUT = RELEASES / f"sigtrades-agent-windows-v{VERSION}.zip"
ALIAS = RELEASES / "sigtrades-agent-windows.zip"

exe = SRC / "sigtrades-agent.exe"
if not exe.is_file():
    raise SystemExit(f"missing exe: {exe}")

RELEASES.mkdir(parents=True, exist_ok=True)
time.sleep(2)
if OUT.exists():
    OUT.unlink()
if ALIAS.exists():
    ALIAS.unlink()

with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in SRC.rglob("*"):
        if path.is_file():
            zf.write(path, arcname=str(Path("sigtrades-agent") / path.relative_to(SRC)))

shutil.copyfile(OUT, ALIAS)
print(f"ZIP_OK path={OUT} size={OUT.stat().st_size}")
