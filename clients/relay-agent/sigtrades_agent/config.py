"""Agent 本地配置与凭证。

关键安全点：富途/IBKR 凭证只存在用户本机此文件，绝不上云。
默认位置：
  - macOS:  ~/Library/Application Support/sigtrades-agent/config.json
  - Windows: %APPDATA%/sigtrades-agent/config.json
  - 其它:   ~/.config/sigtrades-agent/config.json
可用环境变量 SIGTRADES_AGENT_HOME 覆盖目录。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List


def default_config_dir() -> Path:
    override = os.getenv("SIGTRADES_AGENT_HOME")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "sigtrades-agent"
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA") or str(Path.home())
        return Path(base) / "sigtrades-agent"
    return Path.home() / ".config" / "sigtrades-agent"


@dataclass
class BrokerProfile:
    """单个本地券商网关配置（凭证仅本机）。

    支持多 gateway profile：同一券商可配置多个 profile（不同 host/port/账户），
    用 `name` 区分；execute_signal 按 account_id 路由到对应 profile。
    """
    broker: str                      # "ibkr" / "futu"
    name: str = ""                   # profile 名称（多 gateway 时区分），默认用 account_id
    enabled: bool = True
    account_id: str = ""             # 兼容旧配置；交易账户以网页端绑定为准，Agent 可不填
    config: Dict[str, Any] = field(default_factory=dict)  # 传给 adapter 的连接参数（host/port 等）

    @property
    def key(self) -> str:
        return self.name or self.account_id or self.broker


def default_broker_profiles() -> List[BrokerProfile]:
    """开箱默认：IBKR TWS 模拟/实盘 + 富途模拟/实盘，均启用。"""
    from sigtrades_agent.futu_presets import FUTU_PRESETS
    from sigtrades_agent.ibkr_presets import IBKR_PRESETS

    profiles = [
        BrokerProfile(
            broker="ibkr",
            name=name,
            account_id=account_id,
            enabled=True,
            config={"host": "127.0.0.1", "port": port, "client_id": client_id},
        )
        for account_id, name, port, client_id in IBKR_PRESETS
    ]
    profiles.extend(
        BrokerProfile(
            broker="futu",
            name=name,
            account_id=account_id,
            enabled=True,
            config={"host": "127.0.0.1", "port": port, "trd_env": trd_env},
        )
        for account_id, name, trd_env, port in FUTU_PRESETS
    )
    return profiles


def ensure_broker_profiles(cfg: "AgentConfig") -> bool:
    """补齐缺失的默认券商 profile；已有项不覆盖用户自定义端口。返回是否有变更。"""
    from sigtrades_agent.futu_presets import FUTU_PRESETS
    from sigtrades_agent.ibkr_presets import IBKR_PRESETS

    changed = False
    # 去掉已废弃的 IB Gateway 预设（仅保留 TWS）
    kept: List[BrokerProfile] = []
    for p in cfg.broker_profiles:
        if p.broker == "ibkr" and (
            p.account_id in {"gateway-paper", "gateway-live"}
            or int(p.config.get("port") or 0) in {4001, 4002}
        ):
            changed = True
            continue
        kept.append(p)
    if changed:
        cfg.broker_profiles = kept

    ibkr_by_account = {
        p.account_id: p for p in cfg.broker_profiles if p.broker == "ibkr" and p.account_id
    }
    ibkr_by_port: Dict[int, BrokerProfile] = {}
    for p in cfg.broker_profiles:
        if p.broker != "ibkr":
            continue
        try:
            port = int(p.config.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if port:
            ibkr_by_port.setdefault(port, p)

    for account_id, name, port, client_id in IBKR_PRESETS:
        existing = ibkr_by_account.get(account_id) or ibkr_by_port.get(port)
        if existing is None:
            cfg.broker_profiles.append(
                BrokerProfile(
                    broker="ibkr",
                    name=name,
                    account_id=account_id,
                    enabled=True,
                    config={"host": "127.0.0.1", "port": port, "client_id": client_id},
                )
            )
            changed = True
            continue
        if existing.account_id != account_id:
            existing.account_id = account_id
            changed = True
        if not existing.name or existing.name in {"IBKR", "demo-acc"}:
            existing.name = name
            changed = True
        existing.config.setdefault("host", "127.0.0.1")
        if "port" not in existing.config or existing.config.get("port") in (None, "", 0):
            existing.config["port"] = port
            changed = True
        if "client_id" not in existing.config or existing.config.get("client_id") in (None, ""):
            existing.config["client_id"] = client_id
            changed = True

    futu_by_account = {
        p.account_id: p for p in cfg.broker_profiles if p.broker == "futu" and p.account_id
    }
    futu_by_env: Dict[str, BrokerProfile] = {}
    for p in cfg.broker_profiles:
        if p.broker != "futu":
            continue
        env = str(p.config.get("trd_env") or "").upper()
        if env:
            futu_by_env.setdefault(env, p)

    for account_id, name, trd_env, port in FUTU_PRESETS:
        existing = futu_by_account.get(account_id) or futu_by_env.get(trd_env)
        if existing is None:
            cfg.broker_profiles.append(
                BrokerProfile(
                    broker="futu",
                    name=name,
                    account_id=account_id,
                    enabled=True,
                    config={"host": "127.0.0.1", "port": port, "trd_env": trd_env},
                )
            )
            changed = True
            continue
        if existing.account_id != account_id:
            existing.account_id = account_id
            changed = True
        if not existing.name or existing.name in {"Futu OpenD", "Futu"}:
            existing.name = name
            changed = True
        existing.config.setdefault("host", "127.0.0.1")
        if "port" not in existing.config or existing.config.get("port") in (None, "", 0):
            existing.config["port"] = port
            changed = True
        if not existing.config.get("trd_env"):
            existing.config["trd_env"] = trd_env
            changed = True
    return changed


@dataclass
class AgentConfig:
    user_token: str = ""
    account_email: str = ""
    device_id: str = ""
    relay_url: str = "wss://agent.sigtrades.com/agent/ws"  # 与 cloud_defaults.DEFAULT_RELAY_WS_URL 保持一致
    language: str = "zh"
    heartbeat_interval: float = 20.0
    reconnect_min: float = 1.0
    reconnect_max: float = 30.0
    broker_profiles: List[BrokerProfile] = field(default_factory=list)

    @property
    def capabilities(self) -> List[str]:
        return sorted({p.broker for p in self.broker_profiles if p.enabled})

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentConfig":
        profiles = [BrokerProfile(**p) for p in d.get("broker_profiles", [])]
        d = {k: v for k, v in d.items() if k != "broker_profiles"}
        return cls(broker_profiles=profiles, **d)


def config_path() -> Path:
    return default_config_dir() / "config.json"


def load_config() -> AgentConfig:
    from sigtrades_agent.cloud_defaults import DEFAULT_RELAY_WS_URL

    path = config_path()
    if not path.exists():
        cfg = AgentConfig(
            device_id=f"dev-{uuid.uuid4().hex[:12]}",
            broker_profiles=default_broker_profiles(),
            relay_url=DEFAULT_RELAY_WS_URL,
        )
        save_config(cfg)
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        cfg = AgentConfig.from_dict(json.load(f))
    dirty = False
    if not cfg.device_id:
        cfg.device_id = f"dev-{uuid.uuid4().hex[:12]}"
        dirty = True
    # 旧默认 relay 迁移到线上 agent.sigtrades.com
    legacy_relays = {
        "",
        "wss://relay.sigtrades.app/agent/ws",
        "ws://localhost:8081/agent/ws",
        "ws://127.0.0.1:8081/agent/ws",
    }
    if (cfg.relay_url or "").strip() in legacy_relays:
        cfg.relay_url = DEFAULT_RELAY_WS_URL
        dirty = True
    # 旧配置若从未写入券商（或只存了空列表），自动启用默认 IBKR/Futu
    if ensure_broker_profiles(cfg):
        dirty = True
    if dirty:
        save_config(cfg)
    return cfg


def save_config(cfg: AgentConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)  # 凭证文件权限收紧
    except OSError:
        pass
