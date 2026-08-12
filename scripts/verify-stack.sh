#!/usr/bin/env bash
# 冒烟验证 Docker 全栈（需已 docker compose up -d）
set -euo pipefail

check() {
  local name="$1" url="$2"
  if curl -sf "$url" >/dev/null; then
    echo "OK  $name  $url"
  else
    echo "FAIL $name  $url"
    exit 1
  fi
}

check "api-server health" "http://localhost:8080/health"
check "ingest health" "http://localhost:8082/health"
check "web" "http://localhost:5173/"
check "web-admin" "http://localhost:5174/"
check "agent-version API" "http://localhost:8080/public/agent-version"

echo ""
echo "登录 API 冒烟（demo 账号）..."
TOKEN=$(curl -sf -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@sigtrades.app","password":"demo1234"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8080/me >/dev/null
echo "OK  demo login + /me"

echo ""
echo "全部通过。浏览器打开："
echo "  用户端   http://localhost:5173"
echo "  管理后台 http://localhost:5174  (token 见 .env ADMIN_TOKEN)"
