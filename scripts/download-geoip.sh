#!/usr/bin/env bash
# 下载 MaxMind GeoLite2 mmdb（需 MAXMIND_LICENSE_KEY）
# 用法: MAXMIND_LICENSE_KEY=xxx ./scripts/download-geoip.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${GEOIP_DIR:-$ROOT/data/geoip}"
KEY="${MAXMIND_LICENSE_KEY:-}"

if [[ -z "$KEY" ]]; then
  echo "请设置 MAXMIND_LICENSE_KEY（MaxMind 账户 → GeoLite2 → License key）"
  exit 1
fi

mkdir -p "$DEST"
BASE="https://download.maxmind.com/app/geoip_download_by_token?edition_id"

download_edition() {
  local edition="$1"
  local out="$DEST/${edition}.tar.gz"
  echo "Downloading $edition..."
  curl -fsSL "${BASE}=${edition}&license_key=${KEY}&suffix=tar.gz" -o "$out"
  tar -xzf "$out" -C "$DEST" --strip-components=1 "*.mmdb" 2>/dev/null || tar -xzf "$out" -C "$DEST" --wildcards "*.mmdb"
  rm -f "$out"
}

download_edition "GeoLite2-City"
download_edition "GeoLite2-Country"

# 归一化文件名
find "$DEST" -name 'GeoLite2-City.mmdb' -exec cp {} "$DEST/GeoLite2-City.mmdb" \; 2>/dev/null || true
find "$DEST" -name 'GeoLite2-Country.mmdb' -exec cp {} "$DEST/GeoLite2-Country.mmdb" \; 2>/dev/null || true

echo "Done. Files in $DEST:"
ls -la "$DEST"/*.mmdb 2>/dev/null || ls -la "$DEST"
