#!/usr/bin/env bash
# 本机打包 Relay Agent → data/agent-releases/
# 用法: ./scripts/package-agent.sh   或   make build-agent

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RELEASES="$ROOT/data/agent-releases"
AGENT_DIR="$ROOT/clients/relay-agent"
PUBLIC_BASE="${AGENT_RELEASES_PUBLIC_BASE:-https://stapi.sigtrades.com/releases}"

mkdir -p "$RELEASES"
cd "$AGENT_DIR"

# 版本策略：
# - 默认：读当前 __version__，自动 +patch，并写回源码（后台加载本地包即可，无需再 +patch）
# - AGENT_PACKAGE_VERSION=x.y.z：使用指定版本（不自动 +1），便于 Mac/Windows 打同一版本
# - AGENT_PACKAGE_NO_BUMP=1：沿用当前版本、不递增
VERSION="$(
  AGENT_PACKAGE_VERSION="${AGENT_PACKAGE_VERSION:-}" \
  AGENT_PACKAGE_NO_BUMP="${AGENT_PACKAGE_NO_BUMP:-}" \
  python3 <<'PY'
import os
import re
from pathlib import Path

init_path = Path("sigtrades_agent/__init__.py")
pyproject = Path("pyproject.toml")
text = init_path.read_text(encoding="utf-8")
m = re.search(r'__version__\s*=\s*["\x27]([^"\x27]+)["\x27]', text)
cur = m.group(1) if m else "0.1.0"

explicit = (os.environ.get("AGENT_PACKAGE_VERSION") or "").strip().lstrip("vV")
no_bump = (os.environ.get("AGENT_PACKAGE_NO_BUMP") or "").strip() in {"1", "true", "yes"}

def bump_patch(v: str) -> str:
    parts = v.split(".")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return v
    while len(nums) < 3:
        nums.append(0)
    nums[2] += 1
    return ".".join(str(n) for n in nums[:3])

if explicit:
    version = explicit
    action = "指定"
elif no_bump:
    version = cur
    action = "保持"
else:
    version = bump_patch(cur)
    action = f"{cur} →"

# 写回源码，保证打进包的版本与清单一致
init_path.write_text(
    re.sub(
        r'__version__\s*=\s*["\x27][^"\x27]+["\x27]',
        f'__version__ = "{version}"',
        text,
        count=1,
    ),
    encoding="utf-8",
)
if pyproject.is_file():
    pt = pyproject.read_text(encoding="utf-8")
    pt2 = re.sub(r'(?m)^version\s*=\s*["\x27][^"\x27]+["\x27]', f'version = "{version}"', pt, count=1)
    if pt2 != pt:
        pyproject.write_text(pt2, encoding="utf-8")

print(version)
print(f"bump:{action} {version}", file=__import__("sys").stderr)
PY
)"

echo "==> 版本: $VERSION"
echo "==> 安装打包依赖..."
python3 -m pip install -q pyinstaller pywebview Pillow pystray
# 券商 SDK 必须装进打包环境，否则 PyInstaller 打不出 IBKR/富途
python3 -m pip install -q ib_async futu-api
python3 -m pip install -q -e "$ROOT/packages/core" -e "$ROOT/packages/protocol" -e .

OS="$(uname -s)"
PLATFORM=""
OUT=""

case "$OS" in
  Darwin)
    PLATFORM="macos"
    echo "==> macOS 打包..."
    python3 build/build_mac.py
    # 主分发：带版本号（下载 URL / 清单以此为准）；另留无版本别名方便本地脚本
    OUT="$RELEASES/sigtrades-agent-macos-v${VERSION}.dmg"
    ALIAS_OUT="$RELEASES/sigtrades-agent-macos.dmg"
    rm -f "$OUT" "$ALIAS_OUT" dist/sigtrades-agent.dmg
    python3 build/make_dmg.py --app dist/sigtrades-agent.app --out "$OUT"
    cp -f "$OUT" "$ALIAS_OUT"
    cp -f "$OUT" dist/sigtrades-agent.dmg
    # 附带 zip：供自动更新静默替换（可选）
    ZIP_OUT="$RELEASES/sigtrades-agent-macos-v${VERSION}.zip"
    ZIP_ALIAS="$RELEASES/sigtrades-agent-macos.zip"
    rm -f "$ZIP_OUT" "$ZIP_ALIAS"
    ditto -c -k --keepParent dist/sigtrades-agent.app "$ZIP_OUT"
    cp -f "$ZIP_OUT" "$ZIP_ALIAS"
    echo "==> 附带 zip（自动更新）: $ZIP_OUT"
    ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    PLATFORM="windows"
    echo "==> Windows 打包..."
    python3 build/build_win.py
    # 附带安装脚本：解压后双击 setup.bat
    cp -f build/windows/Install.ps1 dist/sigtrades-agent/Install.ps1
    cp -f build/windows/setup.bat dist/sigtrades-agent/setup.bat
    cp -f build/windows/INSTALL.txt dist/sigtrades-agent/INSTALL.txt
    # 可选：若本机装了 Inno Setup，生成正式 Setup.exe
    ISCC=""
    for cand in \
      "/c/Program Files (x86)/Inno Setup 6/ISCC.exe" \
      "/c/Program Files/Inno Setup 6/ISCC.exe" \
      "C:/Program Files (x86)/Inno Setup 6/ISCC.exe" \
      "C:/Program Files/Inno Setup 6/ISCC.exe"; do
      if [ -x "$cand" ] || [ -f "$cand" ]; then ISCC="$cand"; break; fi
    done
    if [ -n "$ISCC" ]; then
      echo "==> 使用 Inno Setup 生成安装包..."
      "$ISCC" build/windows/sigtrades-agent.iss || true
      if [ -f dist/sigtrades-agent-setup.exe ]; then
        cp -f dist/sigtrades-agent-setup.exe "$RELEASES/sigtrades-agent-windows-setup-v${VERSION}.exe"
        cp -f dist/sigtrades-agent-setup.exe "$RELEASES/sigtrades-agent-windows-setup.exe"
        echo "==> Setup.exe: $RELEASES/sigtrades-agent-windows-setup-v${VERSION}.exe"
      fi
    else
      echo "==> 未检测到 Inno Setup，分发 zip + setup.bat（解压后双击安装）"
    fi
    OUT="$RELEASES/sigtrades-agent-windows-v${VERSION}.zip"
    ALIAS_OUT="$RELEASES/sigtrades-agent-windows.zip"
    rm -f "$OUT" "$ALIAS_OUT"
    cd dist
    zip -r "$OUT" sigtrades-agent
    cd "$AGENT_DIR"
    cp -f "$OUT" "$ALIAS_OUT"
    ;;
  *)
    echo "当前系统 ($OS) 无 PyInstaller 一键包，请在本机 Mac/Windows 执行本脚本。"
    exit 1
    ;;
esac

BUILT_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# 刷新清单：刚打的平台用新版本；另一平台若已有包则保留其原版本/SHA（避免误标）
export RELEASES PLATFORM VERSION OUT PUBLIC_BASE BUILT_AT
python3 <<'PY'
import hashlib
import json
import os
from pathlib import Path

releases = Path(os.environ["RELEASES"])
base = os.environ["PUBLIC_BASE"].rstrip("/")
version = os.environ["VERSION"]
built_at = os.environ["BUILT_AT"]
just_built = os.environ["PLATFORM"]

def versioned_name(plat: str, ver: str) -> str:
    if plat == "macos":
        return f"sigtrades-agent-macos-v{ver}.dmg"
    return f"sigtrades-agent-windows-v{ver}.zip"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

manifest_path = releases / "latest-manifest.json"
old: dict = {}
if manifest_path.is_file():
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        old = {}
old_platforms = old.get("platforms") if isinstance(old.get("platforms"), dict) else {}

platforms = {}
for plat in ("macos", "windows"):
    prev = old_platforms.get(plat) if isinstance(old_platforms.get(plat), dict) else {}
    if plat == just_built:
        filename = versioned_name(plat, version)
        path = releases / filename
        if not path.is_file():
            continue
        platforms[plat] = {
            "platform": plat,
            "version": version,
            "filename": filename,
            "path": str(path.resolve()),
            "download_url": f"{base}/{filename}",
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "built_at": built_at,
        }
        continue

    # 另一平台：优先沿用清单里的带版本文件名
    filename = str(prev.get("filename") or "").strip() or versioned_name(plat, str(prev.get("version") or version))
    path = releases / filename
    if not path.is_file():
        # 回退无版本别名
        alias = "sigtrades-agent-macos.dmg" if plat == "macos" else "sigtrades-agent-windows.zip"
        path = releases / alias
        filename = alias if path.is_file() else filename
    if not path.is_file():
        continue
    sha = str(prev.get("sha256") or "").strip().lower()
    prev_size = prev.get("size_bytes")
    size = path.stat().st_size
    if not sha or prev_size is None or int(prev_size) != int(size) or str(prev.get("filename") or "") != filename:
        sha = sha256_file(path)
    platforms[plat] = {
        "platform": plat,
        "version": str(prev.get("version") or version),
        "filename": filename,
        "path": str(path.resolve()),
        "download_url": f"{base}/{filename}",
        "sha256": sha,
        "size_bytes": size,
        "built_at": prev.get("built_at") or built_at,
    }

# 顶层 version = 刚打包平台的版本（后台加载优先用这个）
payload = {"version": version, "updated_at": built_at, "platforms": platforms}
manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("wrote", manifest_path)
for plat in ("macos", "windows"):
    row = platforms.get(plat)
    if row:
        print(f"  [{plat}] OK  v{row['version']}  {row['filename']}  sha256={row['sha256'][:16]}…")
    else:
        print(f"  [{plat}] 缺失 — 请在对应系统执行 make build-agent")
PY

echo ""
echo "=========================================="
echo "本机已打包: $PLATFORM v$VERSION → $OUT"
echo "说明: 版本已自动写入清单；后台点「加载本地包」即可带上 v$VERSION。"
echo "      另一平台若要打同一版本：AGENT_PACKAGE_VERSION=$VERSION make build-agent"
echo "=========================================="
