"""打包进 Agent 的线上默认地址（可被环境变量覆盖）。"""

# Relay WebSocket（agent.sigtrades.com → relay-gateway）
DEFAULT_RELAY_WS_URL = "wss://agent.sigtrades.com/agent/ws"

# 云端 API（浏览器登录 / me / 版本检查）
DEFAULT_API_URL = "https://stapi.sigtrades.com"

# 用户控制台（浏览器登录页、打开控制台）
DEFAULT_WEB_URL = "https://sigtrades.com"

# 版本检查
DEFAULT_VERSION_CHECK_URL = f"{DEFAULT_API_URL}/public/agent-version"
