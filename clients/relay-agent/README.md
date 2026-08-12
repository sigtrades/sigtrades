# sigtrades Relay Agent

桌面 Relay Agent：本机执行 IBKR / 富途，内置 React 设置界面（pywebview），凭证仅存本机。

## 架构

```
sigtrades-agent (Python)
├── Relay WS + 券商执行器
├── 本机 API  :17890  (/api/*, /discord/*)
├── 内置 UI   :17890/ui/  (Vite 构建的静态 React，打包进安装目录)
└── pywebview 桌面窗口 (420×560)
```

## 开发

```bash
# 1. 安装 Python 依赖
cd clients/relay-agent
pip install -e ../../packages/core -e ../../packages/protocol -e .
pip install pywebview ib_async futu-api   # 按需

# 2. 构建 UI
cd ui && npm install && npm run build && cd ..

# 3. 启动（默认打开桌面窗口）
SIGTRADES_AUTO_UPDATE=false sigtrades-agent

# 纯后台（无窗口，适合 CI / 服务器）
sigtrades-agent --no-window

# UI 热更新开发（另开终端跑 Agent，再跑 Vite）
cd ui && npm run dev   # http://localhost:5175/ui/
```

环境变量（可选）：

```bash
export SIGTRADES_API_URL=http://localhost:8080
export SIGTRADES_WEB_URL=http://localhost:5173
```

## 配置

`~/Library/Application Support/sigtrades-agent/config.json`（macOS）

- `user_token` — 浏览器登录写入
- `relay_url` — 默认 `ws://localhost:8081/agent/ws`（本地 Docker）
- `broker_profiles` — IBKR / 富途网关（仅本机）

浏览器登录会打开平台的 `/agent/connect` 授权页。授权完成后 Agent
通过云端一次性会话自动领取 Token；浏览器留在网站成功页，不会跳转本机 `17890/ui`。

## 打包（PyInstaller onedir — 当前最小可行方案）

不走 Electron：Python + 内置静态 UI + pywebview，产物为 PyInstaller **onedir**（macOS 再包成 `.app`）。

```bash
# 推荐：仓库根目录一键打包（当前 OS 对应平台）
make build-agent
# 等价: ./scripts/package-agent.sh
# 默认会把 __version__ 自动 +patch（如 0.1.0 → 0.1.1），并写入 latest-manifest.json
# 指定版本（不递增，便于 Mac/Windows 打同一号）：AGENT_PACKAGE_VERSION=0.1.1 make build-agent
# macOS 产物：data/agent-releases/sigtrades-agent-macos.dmg
# Windows：data/agent-releases/sigtrades-agent-windows.zip
```

打完后打开后台 **Agent 发布** →「加载本地包」自动填下载地址 / SHA256 / 打包版本号 →「发布此版本」。

体积控制要点：
- **onedir**（非 onefile）：启动更快，updater/资源路径更稳
- spec 排除 `matplotlib/PyQt*`；`numpy`/`pandas`/`ib_async`/`futu-api` 会打进包（`package-agent.sh` 会安装券商 SDK）
- 图标来自 `ui/public/logo.png`（macOS 预烘焙 squircle）

## 线程模型

- 主线程：pywebview 窗口
- 后台线程：asyncio（Relay WS + 本机 API + Discord 桥接）
- 券商执行器：各自 worker 线程
