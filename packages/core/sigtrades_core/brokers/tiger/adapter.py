#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
老虎证券适配器实现
Tiger Securities Adapter Implementation
"""

import os
import sys
import json
import logging
import tempfile
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

# 云端模式：Tiger SDK (tigeropen) 作为常规依赖安装，不再依赖本地 master/ 目录。
try:
    from tigeropen.tiger_open_config import TigerOpenClientConfig
    from tigeropen.common.consts import Language, OrderStatus, ComboType, Market, SecurityType, Currency
    from tigeropen.trade.trade_client import TradeClient
    from tigeropen.common.util.order_utils import combo_order, contract_leg, market_order, limit_order
    from tigeropen.common.util.contract_utils import option_contract_by_symbol, stock_contract
except ImportError as e:
    logging.warning(f"无法导入 Tiger API 模块: {e}，某些功能可能不可用")
    TigerOpenClientConfig = None
    TradeClient = None
    combo_order = None
    contract_leg = None
    market_order = None
    limit_order = None
    option_contract_by_symbol = None
    stock_contract = None

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.signal.models import Signal, OptionLeg
from sigtrades_core.signal.option_symbol import (
    ParsedOption,
    format_tiger_option_identifier,
    parse_option_symbol,
)
from sigtrades_core.brokers.status_mapping import TigerStatusMapper, map_tiger_status
from sigtrades_core.trading.order_status import OrderStatus as StandardOrderStatus, get_status_info


logger = logging.getLogger(__name__)

# 纽约时区
NY_TIMEZONE = ZoneInfo("America/New_York")


def _is_tiger_rate_limit(msg: str) -> bool:
    """仅识别真正的频控（SDK code=5 / HTTP 429），勿把 1200+forbidden 当限流。"""
    text = msg or ""
    lower = text.lower()
    if "code=5" in lower or "rate limit error" in lower or "429" in lower:
        return True
    if "too many requests" in lower:
        return True
    # 1200 prime forbidden:Please try again later → 多为账户侧拒绝，不是限流
    if "code=1200" in lower or "prime account" in lower:
        return False
    return "请稍后再试" in text or "try again later" in lower


def _is_tiger_account_forbidden(msg: str) -> bool:
    """code=1200 + forbidden：多为配置账户被拒，不是限流。"""
    text = msg or ""
    lower = text.lower()
    return "code=1200" in lower and (
        "try again later" in lower or "请稍后再试" in text or "forbidden" in lower
    )


def _is_tiger_paper_account(account: Optional[str]) -> bool:
    try:
        from tigeropen.common.util.account_util import AccountUtil

        return bool(AccountUtil.is_paper_account(account))
    except Exception:  # noqa: BLE001
        return bool(account and str(account).isdigit() and len(str(account)) >= 17)


class TigerBrokerAdapter(BaseBrokerAdapter):
    """老虎证券适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化老虎证券适配器
        
        Args:
            config: 券商配置，包含：
                - private_key: 私钥内容（优先 PKCS#1 / private_key_pk1，兼容 pk8）或配置文件路径
                - license: License（可选，默认TBNZ）
                - env: "production"（默认）或 "test"；模拟盘账号也应使用 production（env=PROD）
                - test / production: 分环境的 tiger_id、account（可选）
                - props_path: 配置文件路径（可选）
                - sandbox: 仅表示独立 sandbox 开发环境（一般不用）；与「模拟盘账户」不是一回事
                
                注意：env=production 时读 production 段；否则读 test 段；缺省回退顶层 tiger_id/account。
                模拟盘由账户号识别（AccountUtil.is_paper_account），不靠 env=test。
        """
        super().__init__(config)
        # private_key 可以是配置文件路径（.properties）或私钥文件路径
        self.private_key = config.get("private_key", "")
        self.props_path = config.get("props_path", "")
        # 向后兼容：仅当 private_key 实际是一个存在的文件路径时，才作为 props_path 使用。
        # 云端模式下 private_key 是私钥内容，不应被当作路径。
        if not self.props_path and self.private_key and os.path.exists(self.private_key):
            self.props_path = self.private_key
        self.license = (config.get("license") or "TBNZ").strip().upper() or "TBNZ"
        # TBHK 等牌照要求 Authorization user token；TBNZ 通常不需要。
        # 云端由 secrets_encrypted.token 注入；本地可由 props / token 文件加载。
        self.token = (config.get("token") or "").strip()
        self.sandbox = config.get("sandbox", False)
        
        # env=paper|live 仅为标识；凭证统一从 production / 顶层读取。
        # 模拟盘与实盘由资金账号区分（AccountUtil），不靠独立 sandbox tiger_id。
        prod_config = config.get("production", {}) or {}
        test_config = config.get("test", {}) or {}
        self.tiger_id = (
            prod_config.get("tiger_id")
            or config.get("tiger_id")
            or test_config.get("tiger_id")
        )
        self.account = (
            prod_config.get("account")
            or config.get("account")
            or test_config.get("account")
        )
        # 适配器内部仍用 production，保证走正式网关；is_paper 由账号决定
        self.env = "production"
        logger.info(
            "使用老虎配置: tiger_id=%s, account=%s, label_env=%s",
            self.tiger_id,
            self.account,
            config.get("env"),
        )
        
        # Tiger API 客户端
        self.client_config = None
        self.trade_client = None
    
    def _create_client_config(self) -> TigerOpenClientConfig:
        """创建 Tiger API 配置。

        云端模式优先：private_key 直接是私钥内容（解密后注入，优先 pk1），
        无需本地 .properties 文件。仅当 private_key 是已存在的文件路径时，
        才回退到传统 props_path 方式（向后兼容本地运行）。
        """
        if not TigerOpenClientConfig:
            raise RuntimeError("Tiger API 模块未安装，无法创建配置")

        pk = (self.private_key or "").strip()
        is_file_path = pk and os.path.exists(pk)

        if pk and not is_file_path:
            # ---- 云端模式：private_key 为私钥内容（pk1/pk8）----
            client_config = TigerOpenClientConfig()
            client_config.private_key = pk
            client_config.language = Language.zh_CN
            if not self.tiger_id or not self.account:
                raise ValueError("云端模式需提供 tiger_id 与 account")
            client_config.tiger_id = self.tiger_id
            client_config.account = self.account
            self._apply_license_and_token(client_config)
            self._apply_paper_and_refresh_domains(client_config)
            logger.info(
                "Tiger 配置创建成功(云端私钥注入): tiger_id=%s, account=%s, license=%s, has_token=%s, is_paper=%s, server_url=%s",
                self.tiger_id,
                self.account,
                self.license,
                bool(getattr(client_config, "token", None)),
                getattr(client_config, "is_paper", None),
                getattr(client_config, "server_url", None),
            )
            return client_config

        # ---- 本地兼容模式：props_path 文件 ----
        props_path = self.props_path or pk
        if not props_path or not os.path.exists(props_path):
            raise ValueError("未提供有效的 Tiger 私钥内容或配置文件路径（private_key 字段）")
        props_path = os.path.abspath(props_path)
        logger.info(f"使用配置文件: {props_path}")

        client_config = TigerOpenClientConfig(props_path=props_path)
        client_config.language = Language.zh_CN
        if self.tiger_id:
            client_config.tiger_id = self.tiger_id
        if self.account:
            client_config.account = self.account
        self._apply_license_and_token(client_config)
        self._apply_paper_and_refresh_domains(client_config)

        logger.info(
            "配置创建成功: tiger_id=%s, account=%s, license=%s, has_token=%s, is_paper=%s, server_url=%s",
            getattr(client_config, "tiger_id", "N/A"),
            getattr(client_config, "account", "N/A"),
            getattr(client_config, "license", "N/A"),
            bool(getattr(client_config, "token", None)),
            getattr(client_config, "is_paper", None),
            getattr(client_config, "server_url", None),
        )

        return client_config

    def _apply_license_and_token(self, client_config: Any) -> None:
        """写入 license，并按牌照注入 user token。

        TBHK 网关要求 Authorization=token，缺省会报
        code=2400 user token cannot be empty。TBNZ 通常可不填。
        本地 props 若已加载 token，仅在显式传入时覆盖。
        """
        if self.license:
            client_config.license = self.license
        existing = (getattr(client_config, "token", None) or "").strip()
        token = self.token or existing
        if token:
            client_config.token = token
        elif self.license == "TBHK":
            raise ValueError(
                "TBHK 牌照需要 user token：请上传 tiger_openapi_token.properties，"
                "或在配置中提供 token 字段"
            )

    def _apply_paper_and_refresh_domains(self, client_config: Any) -> None:
        """按账户号识别模拟盘并刷新交易域名。

        老虎文档：模拟盘/实盘下单都走正式环境（env=PROD）；sandbox 是另一套
        tiger_id。模拟盘由 17 位账户号识别（AccountUtil.is_paper_account），
        SDK 会把 is_paper 路由到 PAPER 域名。设置 account 后必须 refresh。
        """
        paper = False
        try:
            from tigeropen.common.util.account_util import AccountUtil

            if AccountUtil.is_paper_account(self.account):
                paper = True
        except Exception:  # noqa: BLE001
            pass
        # 显式 sandbox 仅用于独立沙箱 tiger_id（少见）；不再把 env=test 当成模拟盘
        if self.sandbox and self.env == "test":
            paper = True
        if paper:
            client_config.is_paper = True
        refresh = getattr(client_config, "refresh_server_info", None)
        if callable(refresh):
            refresh()
    
    def connect(self) -> bool:
        """连接到老虎证券 API"""
        self.connect_error = None
        try:
            if not TigerOpenClientConfig or not TradeClient:
                self.connect_error = "Tiger API 模块未安装"
                logger.error(self.connect_error)
                self.connected = False
                return False
            
            # 创建配置
            self.client_config = self._create_client_config()
            
            # 创建交易客户端
            self.trade_client = TradeClient(self.client_config)
            
            ok, probe_err = self._probe_account()
            if ok:
                self.connected = True
                self.connect_error = None
                return True
            self.connected = False
            if probe_err and _is_tiger_rate_limit(probe_err):
                self.connect_error = f"老虎 API 限流: {probe_err}"
            elif probe_err and _is_tiger_account_forbidden(probe_err):
                # 模拟盘/实盘都走 env=PROD；1200 多为该资金账号被拒，不是该改成 test/sandbox
                if "配置账户" in probe_err and "被老虎拒绝" in probe_err:
                    self.connect_error = f"老虎连接失败: {probe_err}"
                else:
                    self.connect_error = (
                        "老虎账户接口拒绝（code=1200 forbidden）。"
                        "模拟盘与实盘均使用正式环境（env=PROD），由资金账号区分；"
                        "请确认 tiger_id/私钥与账户匹配，该模拟账户在老虎 APP/OpenAPI 可交易，"
                        f"且 SDK 已按账户刷新交易域名。原始错误: {probe_err}"
                    )
            else:
                self.connect_error = f"老虎连接失败: {probe_err or '未知错误'}"
            logger.error(self.connect_error)
            return False
                
        except Exception as e:
            logger.error(f"连接老虎证券 API 失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            self.connected = False
            self.connect_error = f"老虎连接失败: {e}"
            return False

    def _probe_account(self) -> tuple[bool, Optional[str]]:
        """探测「当前配置账户」是否可交易。

        不得用 get_managed_accounts 冒充成功：同 tiger_id 下可能同时挂着
        可用的实盘账户与被拒绝的模拟账户；列出账户 ≠ 配置账户可下单。
        """
        if not self.trade_client:
            return False, "trade_client 未初始化"
        errors: List[str] = []
        configured = self.account or getattr(self.client_config, "account", None)

        def _try(name: str, fn) -> bool:
            for attempt in range(1, 3):
                try:
                    result = fn()
                    if result is None or (isinstance(result, list) and len(result) == 0):
                        errors.append(f"{name}: empty")
                        return False
                    acc = getattr(result[0] if isinstance(result, list) else result, "account", None)
                    logger.info(
                        "老虎连接探测成功 via %s configured=%s account=%s",
                        name,
                        configured,
                        acc or "N/A",
                    )
                    return True
                except Exception as e:  # noqa: BLE001
                    msg = str(e)
                    errors.append(f"{name}: {msg}")
                    logger.error("连接探测失败 %s attempt=%s: %s", name, attempt, msg)
                    if _is_tiger_rate_limit(msg) and attempt < 2:
                        time.sleep(1.5 * attempt)
                        continue
                    return False
            return False

        if _try(
            "get_prime_assets",
            lambda: self.trade_client.get_prime_assets(
                account=configured or None,
                base_currency="USD",
                consolidated=True,
            ),
        ):
            return True, None
        if _try(
            "get_assets",
            lambda: self.trade_client.get_assets(account=configured or None),
        ):
            return True, None

        # 辅助信息：列出同 tiger_id 下可用账户，便于区分「密钥有效但该模拟盘不可用」
        managed_hint = ""
        try:
            managed = self.trade_client.get_managed_accounts()
            if managed:
                rows = managed if isinstance(managed, list) else [managed]
                accs = [str(getattr(x, "account", x)) for x in rows]
                managed_hint = f"；同 tiger_id 可见账户={accs}（配置账户={configured} 资产接口仍失败）"
                logger.warning(
                    "配置账户资产不可用，managed_accounts=%s configured=%s",
                    accs,
                    configured,
                )
        except Exception as e:  # noqa: BLE001
            managed_hint = f"；get_managed_accounts 也失败: {e}"

        detail = " | ".join(errors) + managed_hint
        if configured and any("forbidden" in e.lower() or "请稍后再试" in e for e in errors):
            return False, (
                f"配置账户 {configured} 被老虎拒绝资产/交易（code=1200 forbidden）。"
                f"密钥与 tiger_id 通常仍有效{managed_hint}。"
                "请在老虎 APP/OpenAPI 确认该模拟账户可交易，或改绑可用账户。"
                f" 原始: {detail}"
            )
        return False, detail
    
    def disconnect(self) -> bool:
        """断开连接"""
        self.connected = False
        self.trade_client = None
        self.client_config = None
        logger.info("已断开老虎证券 API 连接")
        return True
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        if not self.connected or not self.trade_client:
            raise RuntimeError("未连接到券商 API")
        
        try:
            # 使用 get_prime_assets 获取账户信息
            # get_prime_assets 可能返回 list 或单个 PortfolioAccount 对象
            portfolio_result = self.trade_client.get_prime_assets(
                account=self.account or None,
                base_currency='USD',
                consolidated=True
            )
            
            # 处理返回结果：可能是列表或单个对象
            portfolio = None
            if portfolio_result:
                if isinstance(portfolio_result, list):
                    if len(portfolio_result) > 0:
                        portfolio = portfolio_result[0]  # 取第一个账户
                    else:
                        logger.warning("无法获取账户信息，返回列表为空")
                        portfolio = None
                else:
                    # 直接返回单个 PortfolioAccount 对象
                    portfolio = portfolio_result
            
            if portfolio:
                # 检查是否有 segments 和 'S' (证券账户)
                if hasattr(portfolio, 'segments') and portfolio.segments and 'S' in portfolio.segments:
                    security_segment = portfolio.segments['S']
                    total_assets = float(security_segment.net_liquidation or 0)
                    return {
                        "account": self.account or "",
                        "account_id": self.account or "",
                        "tiger_id": self.tiger_id or "",
                        "is_paper": _is_tiger_paper_account(self.account),
                        "net_liquidation": total_assets,
                        "total_assets": total_assets,
                        "available_cash": float(security_segment.cash_available_for_trade or 0),
                        "positions_value": float(security_segment.gross_position_value or 0),
                        "equity": float(security_segment.equity_with_loan or 0),
                        "margin_used": float(security_segment.init_margin or 0),
                        "unrealized_pl": float(security_segment.unrealized_pl or 0),
                        "realized_pl": float(security_segment.realized_pl or 0)
                    }
                else:
                    logger.warning(f"无法获取证券账户信息，segments: {getattr(portfolio, 'segments', None)}")
                    return {
                        "account": self.account or "",
                        "account_id": self.account or "",
                        "tiger_id": self.tiger_id or "",
                        "is_paper": _is_tiger_paper_account(self.account),
                        "net_liquidation": 0.0,
                        "total_assets": 0.0,
                        "available_cash": 0.0,
                        "positions_value": 0.0,
                        "equity": 0.0,
                        "margin_used": 0.0,
                        "unrealized_pl": 0.0,
                        "realized_pl": 0.0
                    }
            else:
                logger.warning("无法获取账户信息，返回为空")
                return {
                    "account": self.account or "",
                    "account_id": self.account or "",
                    "tiger_id": self.tiger_id or "",
                    "is_paper": _is_tiger_paper_account(self.account),
                    "net_liquidation": 0.0,
                    "total_assets": 0.0,
                    "available_cash": 0.0,
                    "positions_value": 0.0,
                    "equity": 0.0,
                    "margin_used": 0.0,
                    "unrealized_pl": 0.0,
                    "realized_pl": 0.0
                }
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
    
    def get_option_positions(self) -> List[Dict[str, Any]]:
        """
        获取期权持仓列表
        
        Returns:
            持仓列表，格式符合 UI 要求
        """
        if not self.connected or not self.trade_client:
            raise RuntimeError("未连接到券商 API")
        
        try:
            # 使用 get_positions 获取期权持仓
            # 根据文档，需要传入 sec_type=SecurityType.OPT 来获取期权持仓
            if not SecurityType:
                raise RuntimeError("SecurityType 未导入")
            
            positions = self.trade_client.get_positions(
                account=self.account or None,
                sec_type=SecurityType.OPT,
                currency=Currency.USD,
                market=Market.US
            )
            
            # 打印原始持仓数据用于调试 (JSON格式)
            logger.info(f"=== 原始持仓查询结果 (JSON格式) ===")
            logger.info(f"从券商获取到 {len(positions)} 条原始持仓记录")
            raw_positions_json = []
            for i, pos in enumerate(positions):
                contract = getattr(pos, 'contract', None)
                raw_pos_data = {
                    "index": i + 1,
                    "quantity": int(pos.quantity or 0),
                    "average_cost": float(pos.average_cost or 0),
                    "market_value": float(pos.market_value or 0),
                    "unrealized_pl": float(getattr(pos, 'unrealized_pl', 0) or 0),
                    "realized_pl": float(getattr(pos, 'realized_pnl', 0) or 0),
                }
                if contract:
                    raw_pos_data["contract"] = {
                        "symbol": getattr(contract, 'symbol', ''),
                        "identifier": getattr(contract, 'identifier', None),
                        "sec_type": str(getattr(contract, 'sec_type', '')),
                        "expiry": getattr(contract, 'expiry', None),
                        "strike": getattr(contract, 'strike', None),
                        "put_call": str(getattr(contract, 'put_call', None)),
                        "multiplier": getattr(contract, 'multiplier', None),
                        "currency": str(getattr(contract, 'currency', '')),
                    }
                raw_positions_json.append(raw_pos_data)
            # 输出JSON格式
            logger.info(f"原始持仓JSON数据:\n{json.dumps(raw_positions_json, indent=2, ensure_ascii=False)}")
            logger.info(f"========================")
            
            # 先收集所有持仓信息
            position_data_list = []
            
            for pos in positions:
                # 从 contract 对象获取合约信息
                contract = getattr(pos, 'contract', None)
                if not contract:
                    continue
                
                # 获取合约代码和类型
                symbol = getattr(contract, 'symbol', '')
                sec_type = getattr(contract, 'sec_type', '')
                
                # 只处理期权持仓
                if sec_type != 'OPT':
                    continue
                
                # 构建期权标识符（从 contract 中获取）
                # 对于期权，contract 可能包含 identifier 或需要从其他字段构建
                identifier = getattr(contract, 'identifier', None) or symbol
                quantity = int(pos.quantity or 0)
                
                # 跳过数量为0的持仓
                if quantity == 0:
                    continue
                
                # 解析期权代码以提取到期日
                try:
                    option_info = parse_option_symbol(identifier if identifier else symbol)
                    expiry = option_info.get('expiry', '')
                    put_call = option_info.get('put_call', 'CALL')
                    strike = option_info.get('strike', 0)
                    base_symbol = option_info.get('symbol', '')
                except Exception:
                    expiry = ''
                    put_call = 'CALL'
                    strike = 0
                    base_symbol = symbol.split()[0] if ' ' in symbol else symbol
                
                # 计算盈亏
                average_cost = float(pos.average_cost or 0)
                market_value = float(pos.market_value or 0)
                unrealized_pl = float(getattr(pos, 'unrealized_pl', 0) or 0)
                
                # 构建腿信息
                leg_data = {
                    "symbol": identifier if identifier else symbol,
                    "type": "Call" if put_call == 'CALL' else "Put",
                    "direction": "买入" if quantity > 0 else "卖出",
                    "quantity": abs(quantity),
                    "cost": f"${average_cost:.2f}",
                    "market_value": f"${market_value:.2f}" if market_value >= 0 else f"-${abs(market_value):.2f}",
                    "price": f"${market_value / abs(quantity):.2f}" if quantity != 0 else "$0.00",
                    "strike": strike,
                    "put_call": put_call,
                    "base_symbol": base_symbol,
                    "expiry": expiry,
                    "raw_quantity": quantity  # 保留原始数量（带正负号）
                }
                
                position_data_list.append(leg_data)
            
            # 按组合分组持仓
            # 改进的组合识别逻辑：
            # 1. 相同标的、相同到期日、相同类型（CALL/PUT）
            # 2. 数量绝对值相同（表示可能是垂直价差）
            # 3. 行权价相邻（相差不超过100点）
            position_groups = {}
            processed_legs = set()
            
            for i, leg_data in enumerate(position_data_list):
                if i in processed_legs:
                    continue
                
                # 查找匹配的腿组成组合
                matched_legs = [leg_data]
                processed_legs.add(i)
                
                for j, other_leg in enumerate(position_data_list):
                    if j in processed_legs or j == i:
                        continue
                    
                    # 检查是否匹配：相同标的、相同到期日、相同类型、数量绝对值相同
                    if (leg_data['base_symbol'] == other_leg['base_symbol'] and
                        leg_data['expiry'] == other_leg['expiry'] and
                        leg_data['type'] == other_leg['type'] and
                        abs(leg_data['quantity']) == abs(other_leg['quantity']) and
                        abs(leg_data['strike'] - other_leg['strike']) <= 100):  # 行权价相差不超过100点
                        matched_legs.append(other_leg)
                        processed_legs.add(j)
                
                # 创建组合或单腿
                if len(matched_legs) > 1:
                    # 组合持仓
                    total_cost = 0
                    total_market_value = 0
                    for leg in matched_legs:
                        leg_cost = abs(float(leg["cost"].replace("$", "").replace(",", "")) * leg["raw_quantity"])
                        leg_market = abs(float(leg["market_value"].replace("$", "").replace(",", "")))
                        total_cost += leg_cost
                        total_market_value += leg_market
                    
                    # 使用第一个腿的信息作为组合标识（包含类型和行权价以避免冲突）
                    combo_key = f"{leg_data['base_symbol']}_{leg_data['expiry']}_{leg_data['type']}_{leg_data['strike']}_{abs(leg_data['quantity'])}"
                    position_groups[combo_key] = {
                        "strategy": "单腿",  # 稍后根据腿数量更新
                        "type": leg_data["type"],
                        "expiry": leg_data["expiry"],
                        "base_symbol": leg_data["base_symbol"],
                        "quantity": abs(leg_data["quantity"]),  # 使用绝对值
                        "cost": total_cost,
                        "market_value": total_market_value,
                        "pnl": 0,  # 稍后计算
                        "pnl_percent": 0,
                        "legs": matched_legs
                    }
                else:
                    # 单腿持仓（包含类型和行权价以避免冲突）
                    combo_key = f"{leg_data['base_symbol']}_{leg_data['expiry']}_{leg_data['type']}_{leg_data['strike']}_{abs(leg_data['quantity'])}_single"
                    position_groups[combo_key] = {
                        "strategy": "单腿",
                        "type": leg_data["type"],
                        "expiry": leg_data["expiry"],
                        "base_symbol": leg_data["base_symbol"],
                        "quantity": abs(leg_data["quantity"]),
                        "cost": abs(float(leg_data["cost"].replace("$", "").replace(",", "")) * leg_data["raw_quantity"]),
                        "market_value": abs(float(leg_data["market_value"].replace("$", "").replace(",", ""))),
                        "pnl": 0,  # 稍后计算
                        "pnl_percent": 0,
                        "legs": [leg_data]
                    }
            
            # 计算盈亏并确定策略类型
            for group_key, group in position_groups.items():
                # 计算总盈亏
                total_pnl = 0
                for leg in group["legs"]:
                    leg_cost = abs(float(leg["cost"].replace("$", "").replace(",", "")) * leg["raw_quantity"])
                    leg_market = abs(float(leg["market_value"].replace("$", "").replace(",", "")))
                    if leg["raw_quantity"] > 0:  # 买入
                        total_pnl += leg_market - leg_cost
                    else:  # 卖出
                        total_pnl += leg_cost - leg_market
                
                group["pnl"] = total_pnl
                
                # 根据腿数量确定策略类型
                if len(group["legs"]) > 1:
                    # 组合持仓，使用 _determine_strategy 方法
                    group["strategy"] = self._determine_strategy(group["legs"])
                else:
                    group["strategy"] = "单腿"
                
                # 计算盈亏百分比
                cost_basis = group["cost"]
                group["pnl_percent"] = (total_pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            # 二次分组：将匹配的 Call 和 Put 垂直价差合并为铁鹰
            # 查找可配对的垂直价差：相同标的 + 相同到期日 + 相同数量 + Call/Put 配对
            merged_groups = {}
            merged_keys = set()
            
            group_keys = list(position_groups.keys())
            for i, key1 in enumerate(group_keys):
                if key1 in merged_keys:
                    continue
                group1 = position_groups[key1]
                
                # 只处理垂直价差
                if group1["strategy"] != "垂直价差":
                    merged_groups[key1] = group1
                    continue
                
                # 查找匹配的另一个垂直价差
                found_match = False
                for j, key2 in enumerate(group_keys):
                    if i >= j or key2 in merged_keys:
                        continue
                    group2 = position_groups[key2]
                    
                    # 检查是否可配对为铁鹰
                    if (group2["strategy"] == "垂直价差" and
                        group1["base_symbol"] == group2["base_symbol"] and
                        group1["expiry"] == group2["expiry"] and
                        group1["quantity"] == group2["quantity"] and
                        group1["type"] != group2["type"]):  # Call 和 Put 配对
                        
                        # 合并为铁鹰
                        merged_key = f"{group1['base_symbol']}_{group1['expiry']}_{group1['quantity']}_iron_condor"
                        merged_groups[merged_key] = {
                            "strategy": "铁鹰",
                            "type": "Call+Put",
                            "expiry": group1["expiry"],
                            "base_symbol": group1["base_symbol"],
                            "quantity": group1["quantity"],
                            "cost": group1["cost"] + group2["cost"],
                            "market_value": group1["market_value"] + group2["market_value"],
                            "pnl": group1["pnl"] + group2["pnl"],
                            "pnl_percent": 0,  # 稍后重新计算
                            "legs": group1["legs"] + group2["legs"]
                        }
                        # 重新计算盈亏百分比
                        total_cost = merged_groups[merged_key]["cost"]
                        total_pnl = merged_groups[merged_key]["pnl"]
                        merged_groups[merged_key]["pnl_percent"] = (total_pnl / total_cost * 100) if total_cost > 0 else 0
                        
                        merged_keys.add(key1)
                        merged_keys.add(key2)
                        found_match = True
                        logger.info(f"合并垂直价差为铁鹰: {group1['type']} + {group2['type']}, 数量={group1['quantity']}")
                        break
                
                if not found_match:
                    merged_groups[key1] = group1
            
            # 使用合并后的分组
            position_groups = merged_groups
            
            # 转换为列表格式
            position_list = []
            for group_key, group in position_groups.items():
                # 重新计算盈亏百分比
                cost_basis = group["cost"]
                pnl_percent = (group["pnl"] / cost_basis * 100) if cost_basis > 0 else 0
                
                position_list.append({
                    "strategy": group["strategy"],
                    "type": group["type"],
                    "expiry": group["expiry"],
                    "quantity": group["quantity"],
                    "cost": f"${group['cost']:.2f}",
                    "market_value": f"${group['market_value']:.2f}",
                    "pnl": f"+${group['pnl']:.2f}" if group['pnl'] >= 0 else f"-${abs(group['pnl']):.2f}",
                    "pnl_percent": f"+{pnl_percent:.2f}%" if pnl_percent >= 0 else f"{pnl_percent:.2f}%",
                    "legs": group["legs"]
                })
            
            # 添加调试日志
            logger.info(f"=== 持仓数据详情 ===")
            logger.info(f"总共 {len(position_list)} 条持仓:")
            for i, pos in enumerate(position_list):
                logger.info(f"  [{i+1}] 策略={pos['strategy']}, 类型={pos['type']}, 到期={pos['expiry']}, 数量={pos['quantity']}")
                logger.info(f"       成本={pos['cost']}, 市值={pos['market_value']}, 盈亏={pos['pnl']} ({pos['pnl_percent']})")
                logger.info(f"       腿数量={len(pos.get('legs', []))}")
                for j, leg in enumerate(pos.get('legs', [])):
                    logger.info(f"         腿{j+1}: {leg.get('symbol')}, {leg.get('direction')} {leg.get('quantity')}, 行权价={leg.get('strike')}, 类型={leg.get('type')}")
            logger.info(f"===================")
            
            return position_list
            
        except Exception as e:
            logger.error(f"获取期权持仓失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
        return []
    
    def _place_stock_order(self, signal: Signal) -> Dict[str, Any]:
        """股票现货下单（STK）：stock_contract + market/limit_order，勿用 combo。"""
        if not self.trade_client or not stock_contract or not market_order or not limit_order:
            return {"order_id": None, "status": "FAILED", "error": "Tiger SDK not loaded"}

        symbol = (signal.symbol or "").strip().upper()
        if not symbol or " " in symbol or not symbol.replace(".", "").isalnum():
            return {
                "order_id": None,
                "status": "FAILED",
                "retryable": False,
                "error": f"无效正股代码: {signal.symbol!r}",
            }

        action = (signal.action or "BUY").upper()
        try:
            quantity = int(signal.quantity or 0)
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            return {
                "order_id": None,
                "status": "FAILED",
                "retryable": False,
                "error": f"订单数量无效: {signal.quantity}",
            }

        order_type = (signal.order_type or "MKT").upper()
        if order_type not in ("MKT", "LMT"):
            logger.warning("不支持的正股订单类型 %s，使用市价单", order_type)
            order_type = "MKT"

        account = self.account or self.client_config.account
        try:
            contract = stock_contract(symbol, "USD")
        except Exception as e:  # noqa: BLE001
            return {
                "order_id": None,
                "status": "FAILED",
                "retryable": False,
                "error": f"创建股票合约失败: {e}",
            }

        logger.info(
            "提交正股订单: %s %s x%s order_type=%s limit=%s account=%s",
            action,
            symbol,
            quantity,
            order_type,
            signal.limit_price,
            account,
        )
        try:
            if order_type == "MKT":
                order = market_order(
                    account=account,
                    contract=contract,
                    action=action,
                    quantity=quantity,
                )
            else:
                if signal.limit_price is None:
                    return {
                        "order_id": None,
                        "status": "FAILED",
                        "retryable": False,
                        "error": "限价单需要提供 limit_price",
                    }
                order = limit_order(
                    account=account,
                    contract=contract,
                    action=action,
                    quantity=quantity,
                    limit_price=float(signal.limit_price),
                )
            self.trade_client.place_order(order)
        except Exception as e:  # noqa: BLE001
            error_msg = str(e)
            detail = f"提交正股订单失败: {error_msg}"
            if "合约不正确" in error_msg:
                detail += f"；已按 STK 提交 symbol={symbol}（非期权组合单）"
            logger.error(detail)
            return {
                "order_id": None,
                "status": "FAILED",
                "retryable": False if "合约不正确" in error_msg or "bad_request" in error_msg.lower() else True,
                "error": detail,
            }

        order_id = str(getattr(order, "id", "") or "")
        return {"order_id": order_id or None, "status": "SUCCESS", "error": None}

    def place_protective_orders(
        self,
        signal: Signal,
        fill_price: float,
        *,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not combo_order or not contract_leg or not self.trade_client:
            return {"status": "skipped"}
        if not self.connected:
            return {"status": "skipped", "error": "not connected"}

        from sigtrades_core.brokers.stock_utils import is_stock_signal

        qty = signal.quantity or 1
        is_long = (signal.action or "BUY").upper() in ("BUY", "OPEN")
        account = self.account or self.client_config.account
        placed = []

        def _combo_legs_for_exit() -> list:
            legs = []
            if signal.legs and len(signal.legs) > 0:
                for leg in signal.legs:
                    try:
                        option_info = parse_option_symbol(leg.symbol)
                    except Exception as e:  # noqa: BLE001
                        raise ValueError(f"parse leg failed: {e}") from e
                    leg_exit = "SELL" if leg.action.upper() == "BUY" else "BUY"
                    legs.append(contract_leg(
                        symbol=option_info["symbol"],
                        sec_type="OPT",
                        expiry=option_info["expiry_contract"],
                        strike=option_info["strike"],
                        put_call=option_info["put_call"],
                        action=leg_exit,
                        ratio=max(1, leg.quantity or 1),
                    ))
            elif is_stock_signal(signal):
                symbol = (signal.symbol or "").upper()
                exit_action = "SELL" if is_long else "BUY"
                legs.append(contract_leg(symbol=symbol, sec_type="STK", action=exit_action, ratio=1))
            else:
                raise ValueError("no legs or stock symbol for protective order")
            return legs

        try:
            legs = _combo_legs_for_exit()
        except ValueError as e:
            return {"status": "FAILED", "error": str(e), "order_ids": []}

        # 与 place_order 组合单一致：combo 级 action 用 BUY，方向由各 leg action 决定
        combo_action = "BUY"
        if stop_loss_pct is not None:
            stop_px = fill_price * (1 - stop_loss_pct / 100) if is_long else fill_price * (1 + stop_loss_pct / 100)
            stop_order = combo_order(
                account, legs, combo_type=ComboType.CUSTOM, action=combo_action,
                quantity=qty, order_type="STP", limit_price=round(stop_px, 2),
            )
            self.trade_client.place_order(stop_order)
            placed.append(str(getattr(stop_order, "id", "")))
        if take_profit_pct is not None:
            tp_px = fill_price * (1 + take_profit_pct / 100) if is_long else fill_price * (1 - take_profit_pct / 100)
            tp_order = combo_order(
                account, legs, combo_type=ComboType.CUSTOM, action=combo_action,
                quantity=qty, order_type="LMT", limit_price=round(tp_px, 2),
            )
            self.trade_client.place_order(tp_order)
            placed.append(str(getattr(tp_order, "id", "")))
        return {"status": "SUCCESS" if placed else "skipped", "order_ids": placed}

    @staticmethod
    def _to_parsed_option(info: Dict[str, Any]) -> ParsedOption:
        return ParsedOption(
            underlying=info["underlying"] or info["symbol"],
            strike=float(info["strike"]),
            right=info["right"],
            put_call=info["put_call"],
            expiry=info["expiry"],
            expiry_contract=info["expiry_contract"],
        )

    def _resolve_option_info(
        self,
        symbol: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        strike: Optional[float] = None,
        right: Optional[str] = None,
    ) -> Dict[str, Any]:
        """解析为老虎四要素，并附带 21 位 OCC identifier（日志/对照用）。"""
        meta = metadata or {}
        info = parse_option_symbol(
            symbol,
            metadata=meta,
            underlying=meta.get("underlying"),
            strike=strike if strike is not None else meta.get("strike"),
            right=right or meta.get("right") or meta.get("option_type"),
            expiry=meta.get("expiry") or meta.get("expiry_date"),
        )
        parsed = self._to_parsed_option(info)
        info["identifier"] = format_tiger_option_identifier(parsed)
        return info

    def place_order(self, signal: Signal) -> Dict[str, Any]:
        """
        提交订单（单个期权或组合订单）
        默认使用市价单（MKT）
        
        Args:
            signal: 交易信号
            
        Returns:
            {
                "order_id": "订单ID",
                "status": "SUCCESS" 或 "FAILED",
                "error": "错误信息（如果有）"
            }
        """
        if not self.connected or not self.trade_client:
            raise RuntimeError("未连接到券商 API")

        from sigtrades_core.brokers.stock_utils import is_stock_signal
        if is_stock_signal(signal):
            return self._place_stock_order(signal)
        
        if not combo_order or not contract_leg:
            raise RuntimeError("Tiger API 订单工具未导入")
        
        try:
            # 确定订单类型（默认使用市价单）
            order_type = signal.order_type if signal.order_type else "MKT"
            if order_type not in ["MKT", "LMT"]:
                logger.warning(f"不支持的订单类型 {order_type}，使用市价单")
                order_type = "MKT"
            
            # 确定订单数量
            quantity = signal.quantity
            if quantity <= 0:
                raise ValueError(f"订单数量无效: {quantity}")
            
            # 创建 legs
            legs = []
            meta = signal.metadata or {}
            
            if signal.legs and len(signal.legs) > 1:
                # 多腿组合：垂直价差须用 ComboType.VERTICAL（官方文档），勿一律 CUSTOM
                logger.info(f"提交组合订单: {len(signal.legs)} 条腿")
                option_infos: List[Dict[str, Any]] = []

                for leg in signal.legs:
                    option_info = self._resolve_option_info(
                        leg.symbol,
                        metadata=meta,
                        strike=getattr(leg, "strike", None),
                        right=getattr(leg, "option_type", None),
                    )
                    option_infos.append(option_info)
                    logger.info(
                        "解析腿 %s %s → OCC=%s underlying=%s expiry=%s strike=%s put_call=%s",
                        leg.action,
                        leg.symbol,
                        option_info["identifier"],
                        option_info["underlying"],
                        option_info["expiry_contract"],
                        option_info["strike"],
                        option_info["put_call"],
                    )

                    # 四要素：symbol + expiry(yyyyMMdd) + strike + put_call(PUT/CALL)
                    leg_obj = contract_leg(
                        symbol=option_info["underlying"] or option_info["symbol"],
                        sec_type="OPT",
                        expiry=option_info["expiry_contract"],
                        strike=float(option_info["strike"]),
                        put_call=option_info["put_call"],  # PUT / CALL
                        action=leg.action,
                        ratio=1,
                    )
                    legs.append(leg_obj)

                combo_type = self._infer_combo_type(option_infos)
                account = self.account or self.client_config.account
                # 与 spx/online combo_lmt 对齐：收入型垂直价差必须用负数限价的限价单。
                from datetime import time as dt_time

                ny_time_combo = datetime.now(NY_TIMEZONE)
                limit_px = self._combo_limit_price(signal, order_type, option_infos)
                credit = self._is_credit_combo(signal, option_infos)
                if credit and signal.limit_price is not None:
                    order_type = "LMT"
                    limit_px = -abs(float(signal.limit_price))
                elif order_type == "MKT":
                    t = ny_time_combo.time()
                    if t < dt_time(9, 30) or t >= dt_time(16, 0):
                        return {
                            "order_id": None,
                            "status": "FAILED",
                            "retryable": False,
                            "error": (
                                "老虎组合单在盘前盘后不能用市价单，请改为限价单并在美东常规交易时段重试。"
                                f" 当前 {ny_time_combo.strftime('%H:%M:%S %Z')}"
                            ),
                        }

                logger.info(
                    "创建组合订单: account=%s, legs=%s, combo_type=%s, action=BUY, quantity=%s, "
                    "order_type=%s, limit_price=%s (raw=%s credit=%s)",
                    account,
                    len(legs),
                    combo_type,
                    quantity,
                    order_type,
                    limit_px,
                    signal.limit_price,
                    credit,
                )

                combo = combo_order(
                    account,
                    legs,
                    combo_type=combo_type,
                    action="BUY",  # 开仓组合；方向由各 leg.action 决定
                    quantity=quantity,
                    order_type=order_type,
                    limit_price=limit_px,
                )
                
                logger.info(f"组合订单对象创建成功: {combo}")
                
                # 提交订单
                logger.info(f"准备提交组合订单，当前时间: {ny_time_combo.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                try:
                    order_response = self.trade_client.place_order(combo)
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"提交组合订单异常: {error_msg}")
                    
                    # 解析错误信息，提供更友好的提示
                    if "合约不正确" in error_msg or "bad_request:合约不正确" in error_msg:
                        occs = [info.get("identifier") for info in option_infos]
                        detail = (
                            "老虎返回合约不正确：请确认到期日/行权价在期权链上真实存在，"
                            f"组合类型={combo_type}，OCC={occs}"
                        )
                        logger.error(detail)
                        return {
                            "order_id": None,
                            "status": "FAILED",
                            "retryable": False,
                            "error": f"提交订单失败: {error_msg}；{detail}",
                        }
                    if _is_tiger_account_forbidden(error_msg) or "请稍后再试" in error_msg:
                        # 实测：同 tiger_id 下实盘账户可查资产，而配置的模拟账户 1200 forbidden。
                        # 模拟/实盘都走 env=PROD，此处是账户侧拒绝，不是该改 sandbox。
                        detail = (
                            f"老虎拒绝配置账户 {self.account} 的交易（code=1200 forbidden）。"
                            "常见原因是该模拟账户本身不可用/被限制（不是限价正负或盘段问题）；"
                            "请到老虎 APP「交易」核对模拟盘状态，或改绑同 tiger_id 下可用账户。"
                            f" order_type={order_type} limit_price={limit_px} "
                            f"server={getattr(self.client_config, 'server_url', None)}"
                        )
                        return {
                            "order_id": None,
                            "status": "FAILED",
                            "retryable": False,
                            "error": f"提交订单失败: {error_msg}；{detail}",
                        }
                    raise
                
                if order_response:
                    # 从 order 对象获取订单ID
                    order_id = getattr(combo, 'id', None)
                    if order_id:
                        order_id = str(order_id)
                        logger.info(f"组合订单提交成功: {order_id}")
                        return {
                            "order_id": order_id,
                            "status": "SUCCESS",
                            "error": None
                        }
                    else:
                        error_msg = "订单提交成功但未返回订单ID"
                        logger.warning(error_msg)
                        return {
                            "order_id": None,
                            "status": "SUCCESS",  # 即使没有ID，也认为提交成功
                            "error": error_msg
                        }
                else:
                    error_msg = "订单提交失败：API 返回失败"
                    logger.error(error_msg)
                    return {
                        "order_id": None,
                        "status": "FAILED",
                        "error": error_msg
                    }
                    
            else:
                # 单个订单 - 使用 market_order 或 limit_order
                logger.info(f"提交单个订单: {signal.action} {signal.symbol} x{quantity}")
                
                # 解析期权代码（老虎：四要素 + 21 位 OCC identifier）
                try:
                    option_info = self._resolve_option_info(signal.symbol, metadata=meta)
                    logger.info(
                        "解析期权代码成功: OCC=%s underlying=%s expiry=%s strike=%s put_call=%s",
                        option_info["identifier"],
                        option_info["underlying"],
                        option_info["expiry_contract"],
                        option_info["strike"],
                        option_info["put_call"],
                    )
                except Exception as e:
                    logger.error(f"解析期权代码失败: {signal.symbol}, 错误: {e}")
                    raise ValueError(f"无效的期权代码格式: {signal.symbol}")
                
                # 创建期权合约对象
                if not option_contract_by_symbol:
                    raise RuntimeError("Tiger API 合约工具未导入")
                
                # 检查交易时间（美股盘前盘后无法下市价单）
                from datetime import time as dt_time
                ny_time = datetime.now(NY_TIMEZONE)
                current_time = ny_time.time()
                MARKET_OPEN = dt_time(9, 30)  # 美东时间 9:30
                MARKET_CLOSE = dt_time(16, 0)  # 美东时间 16:00
                
                if order_type == 'MKT' and (current_time < MARKET_OPEN or current_time >= MARKET_CLOSE):
                    error_msg = f"美股盘前盘后阶段无法下市价单。当前时间: {current_time.strftime('%H:%M:%S')} (美东时间)"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                und = option_info["underlying"] or option_info["symbol"]
                # 根据文档，option_contract_by_symbol 的 expiry 参数应该是 '20200110' 格式（YYYYMMDD，8位数字）
                contract = option_contract_by_symbol(
                    und,
                    option_info['expiry_contract'],
                    strike=option_info['strike'],
                    put_call=option_info['put_call'],
                    currency='USD'
                )
                
                logger.info(
                    "创建期权合约: OCC=%s symbol=%s expiry=%s strike=%s put_call=%s",
                    option_info["identifier"],
                    und,
                    option_info["expiry_contract"],
                    option_info["strike"],
                    option_info["put_call"],
                )
                logger.info(f"合约详情: {contract}")
                
                # 根据订单类型创建订单
                if order_type == 'MKT':
                    if not market_order:
                        raise RuntimeError("Tiger API market_order 未导入")
                    order = market_order(
                        account=self.account or self.client_config.account,
                        contract=contract,
                        action=signal.action,
                        quantity=quantity
                    )
                    logger.info(f"创建市价单: account={self.account or self.client_config.account}, action={signal.action}, quantity={quantity}, time_in_force={signal.time_in_force}")
                else:
                    if not limit_order:
                        raise RuntimeError("Tiger API limit_order 未导入")
                    if not signal.limit_price:
                        raise ValueError("限价单需要提供 limit_price")
                    order = limit_order(
                        account=self.account or self.client_config.account,
                        contract=contract,
                        action=signal.action,
                        quantity=quantity,
                        limit_price=signal.limit_price
                    )
                    logger.info(f"创建限价单: account={self.account or self.client_config.account}, action={signal.action}, quantity={quantity}, limit_price={signal.limit_price}, time_in_force={signal.time_in_force}")
                
                # 提交订单
                logger.info(f"准备提交订单，当前时间: {ny_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                order_response = self.trade_client.place_order(order)
                
                if order_response:
                    # 从 order 对象获取订单ID
                    order_id = getattr(order, 'id', None)
                    if order_id:
                        order_id = str(order_id)
                        logger.info(f"单个订单提交成功: {order_id}")
                        return {
                            "order_id": order_id,
                            "status": "SUCCESS",
                            "error": None
                        }
                    else:
                        error_msg = "订单提交成功但未返回订单ID"
                        logger.warning(error_msg)
                        return {
                            "order_id": None,
                            "status": "SUCCESS",  # 即使没有ID，也认为提交成功
                            "error": error_msg
                        }
                else:
                    error_msg = "订单提交失败：API 返回失败"
                    logger.error(error_msg)
                    return {
                        "order_id": None,
                        "status": "FAILED",
                        "error": error_msg
                    }
                    
        except Exception as e:
            error_msg = f"提交订单失败: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            if "请稍后再试" in error_msg or "too many" in error_msg.lower():
                retryable = True
            elif "合约不正确" in error_msg:
                retryable = False
            elif "bad_request" in error_msg.lower():
                retryable = False
            else:
                retryable = True
            return {
                "order_id": None,
                "status": "FAILED",
                "retryable": retryable,
                "error": error_msg,
            }
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        查询单个订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            订单信息字典，如果未找到返回 None
        """
        if not self.connected or not self.trade_client:
            raise RuntimeError("未连接到券商 API")
        
        try:
            # 使用 Tiger API 的 get_order 方法直接查询单个订单
            # Tiger API 需要整数类型的订单ID
            # show_charges=True 用于获取费用详情
            order_id_int = int(order_id) if isinstance(order_id, str) else order_id
            order = self.trade_client.get_order(id=order_id_int, show_charges=True)
            
            if not order:
                logger.debug(f"未找到订单: {order_id}")
                return None
            
            # 打印订单原始信息用于调试
            logger.debug(f"订单原始信息: {order}")
            
            # 获取订单状态
            order_status_raw = getattr(order, 'status', 'UNKNOWN')
            if hasattr(order_status_raw, 'name'):
                order_status = order_status_raw.name
            elif hasattr(order_status_raw, 'value'):
                order_status = str(order_status_raw.value)
            else:
                order_status = str(order_status_raw)
            
            # 检查是否有 contract_legs（组合订单）
            contract_legs = getattr(order, 'contract_legs', None)
            contract = getattr(order, 'contract', None)
            
            # 获取成交价和订单类型（原始值）
            avg_fill_price = getattr(order, 'avg_fill_price', None)
            order_type_raw = getattr(order, 'order_type', '')
            if hasattr(order_type_raw, 'name'):
                order_type_raw = order_type_raw.name
            elif hasattr(order_type_raw, 'value'):
                order_type_raw = str(order_type_raw.value)
            else:
                order_type_raw = str(order_type_raw)
            
            # 获取成交金额和费用
            filled_cash_amount = getattr(order, 'filled_cash_amount', None)
            commission = getattr(order, 'commission', None)
            gst = getattr(order, 'gst', None)  # 税费
            realized_pnl = getattr(order, 'realized_pnl', None)  # 已实现盈亏（平仓时有值）
            
            # 如果 filled_cash_amount 为空，根据成交价和数量计算
            # 成交金额 = |成交价| * 数量 * 100（期权乘数）
            if filled_cash_amount is None and avg_fill_price is not None:
                quantity = int(getattr(order, 'quantity', 0))
                filled_cash_amount = abs(float(avg_fill_price)) * quantity * 100
            
            # 构建订单信息
            order_info = {
                "order_id": str(order.id) if hasattr(order, 'id') else order_id,
                "status": self._translate_status(order_status),
                "standard_status": self._get_standard_status(order_status),  # 标准化状态（用于存储和跨券商统一）
                "raw_status": order_status,  # 原始状态
                "order_type": self._translate_order_type(order_type_raw),
                "order_type_raw": order_type_raw,  # 原始订单类型（MKT/LMT等）
                "quantity": int(getattr(order, 'quantity', 0)),
                "filled": int(getattr(order, 'filled', 0)),
                "remaining": int(getattr(order, 'remaining', 0)),
                "avg_fill_price": float(avg_fill_price) if avg_fill_price else None,  # 成交均价
                "limit_price": float(order.limit_price) if hasattr(order, 'limit_price') and order.limit_price else None,
                "filled_cash_amount": float(filled_cash_amount) if filled_cash_amount else None,  # 成交金额
                "commission": float(commission) if commission else None,  # 佣金
                "gst": float(gst) if gst else None,  # 税费
                "realized_pnl": float(realized_pnl) if realized_pnl else None,  # 已实现盈亏
                "time": self._format_time(getattr(order, 'order_time', None) or getattr(order, 'create_time', None)),
                "price": f"${order.limit_price:.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-"
            }
            
            # 如果是组合订单，添加 legs 信息
            if contract_legs and len(contract_legs) > 1:
                legs = []
                for leg in contract_legs[:4]:  # 最多4条腿
                    # contract_legs 里面是 OrderContractLeg 对象，需要用 getattr 访问属性
                    symbol = getattr(leg, 'symbol', '')
                    expiry = getattr(leg, 'expiry', '')
                    put_call = getattr(leg, 'put_call', '')
                    strike = getattr(leg, 'strike', 0) or 0
                    action = getattr(leg, 'action', 'BUY')
                    ratio = getattr(leg, 'ratio', 1) or 1
                    
                    # 格式化期权代码
                    try:
                        strike_val = float(strike) if strike else 0
                        option_code = f"{symbol}  {expiry}{put_call}{int(strike_val * 1000):08d}"
                    except (ValueError, TypeError):
                        option_code = f"{symbol}  {expiry}{put_call}"
                    
                    legs.append({
                        "symbol": option_code,
                        "direction": "买入" if action == "BUY" else "卖出",
                        "quantity": int(ratio),
                        "status": self._translate_status(order_status)
                    })
                
                order_info["legs"] = legs
                order_info["strategy"] = self._determine_strategy(legs)
                order_info["direction"] = "组合"
            else:
                # 单个订单
                if contract:
                    symbol = getattr(contract, 'identifier', None) or getattr(contract, 'symbol', '')
                else:
                    symbol = ''
                
                order_info["legs"] = [{
                    "symbol": symbol,
                    "direction": "买入" if (hasattr(order, 'action') and order.action == 'BUY') else "卖出",
                    "quantity": int(getattr(order, 'quantity', 0)),
                    "status": self._translate_status(order_status)
                }]
                order_info["strategy"] = "单腿"
                order_info["direction"] = "买入" if (hasattr(order, 'action') and order.action == 'BUY') else "卖出"
            
            return order_info
            
        except Exception as e:
            logger.warning(f"查询单个订单失败: {order_id}, 错误: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        if not self.connected or not self.trade_client:
            raise RuntimeError("未连接到券商 API")
        
        try:
            # Tiger API 需要整数类型的订单ID
            order_id_int = int(order_id) if isinstance(order_id, str) else order_id
            result = self.trade_client.cancel_order(id=order_id_int)
            if result:
                logger.info(f"订单撤销成功: {order_id}")
                return True
            else:
                logger.warning(f"订单撤销失败: {order_id}")
                return False
        except Exception as e:
            logger.error(f"撤销订单失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        查询订单列表
        
        Args:
            status: 订单状态筛选（可选），如 'FILLED', 'NEW', 'CANCELLED' 等
        
        Returns:
            订单列表，格式符合 UI 要求
        """
        if not self.connected or not self.trade_client:
            raise RuntimeError("未连接到券商 API")
        
        try:
            # 获取期权订单列表
            # 根据文档，需要传入 sec_type=SecurityType.OPT 来获取期权订单
            if not SecurityType:
                raise RuntimeError("SecurityType 未导入")
            
            orders = self.trade_client.get_orders(
                account=self.account or None,
                sec_type=SecurityType.OPT,
                market=Market.US,
                limit=100  # 默认获取100条订单
            )
            
            # 先收集所有订单信息，用于后续组合识别
            raw_orders = []
            for order in orders:
                # 获取订单状态，可能是枚举对象或字符串
                order_status_raw = getattr(order, 'status', 'UNKNOWN')
                
                # 如果是枚举对象，获取其名称或值
                if hasattr(order_status_raw, 'name'):
                    order_status = order_status_raw.name
                elif hasattr(order_status_raw, 'value'):
                    order_status = str(order_status_raw.value)
                else:
                    order_status = str(order_status_raw)
                
                # 如果指定了状态筛选，则过滤
                if status and order_status != status:
                    continue
                
                # 从 contract 对象获取合约信息（单个订单）
                # 或从 contract_legs 获取组合订单信息
                contract = getattr(order, 'contract', None)
                contract_legs = getattr(order, 'contract_legs', None)
                
                # 检查是否是期权订单
                if contract:
                    sec_type = getattr(contract, 'sec_type', '')
                    if sec_type != 'OPT':
                        continue
                elif not contract_legs:
                    # 既没有 contract 也没有 contract_legs，跳过
                    continue
                
                # 获取订单时间（用于组合识别）
                order_time = getattr(order, 'order_time', None) or getattr(order, 'create_time', None)
                
                raw_orders.append({
                    'order': order,
                    'contract': contract,
                    'contract_legs': contract_legs,
                    'status': order_status,
                    'order_time': order_time
                })
            
            # 处理订单，识别组合关系
            order_list = []
            processed_order_ids = set()
            
            for raw_order_data in raw_orders:
                order = raw_order_data['order']
                contract = raw_order_data['contract']
                contract_legs = raw_order_data['contract_legs']
                order_status = raw_order_data['status']
                order_time = raw_order_data['order_time']
                order_id = str(order.id) if hasattr(order, 'id') else ''
                
                # 如果已经处理过，跳过
                if order_id in processed_order_ids:
                    continue
                
                # 处理组合订单（有 contract_legs 且数量 > 1）
                # 注意：如果 contract_legs 超过4条，可能是错误的组合，只处理前4条
                if contract_legs and len(contract_legs) > 1:
                    # 组合订单
                    legs = []
                    # 限制最多处理4条腿（正常的期权组合最多4条腿：铁鹰策略）
                    max_legs = min(len(contract_legs), 4)
                    for i, leg in enumerate(contract_legs[:max_legs]):
                        # contract_legs 里面是 OrderContractLeg 对象，需要用 getattr 访问属性
                        symbol = getattr(leg, 'symbol', '')
                        expiry = getattr(leg, 'expiry', '')
                        put_call = getattr(leg, 'put_call', '')
                        strike = getattr(leg, 'strike', 0) or 0
                        action = getattr(leg, 'action', 'BUY')
                        ratio = getattr(leg, 'ratio', 1) or 1
                        
                        # 老虎展示用 21 位 OCC（标的右填空格至 6）
                        type_char = "C" if str(put_call).upper() in ("CALL", "C") else "P"
                        try:
                            strike_val = float(strike) if strike else 0.0
                            expiry_full = str(expiry or "").replace("-", "")
                            if len(expiry_full) == 6:
                                expiry_full = f"20{expiry_full}"
                            option_symbol = format_tiger_option_identifier(
                                ParsedOption(
                                    underlying=str(symbol or "").strip().upper(),
                                    strike=strike_val,
                                    right=type_char,
                                    put_call="CALL" if type_char == "C" else "PUT",
                                    expiry=(
                                        f"{expiry_full[:4]}-{expiry_full[4:6]}-{expiry_full[6:8]}"
                                        if len(expiry_full) == 8
                                        else ""
                                    ),
                                    expiry_contract=expiry_full if len(expiry_full) == 8 else "19700101",
                                )
                            )
                        except (ValueError, TypeError):
                            option_symbol = f"{symbol} {expiry}{type_char}{strike}"
                        
                        legs.append({
                            "symbol": option_symbol,
                            "direction": "买入" if action == 'BUY' else "卖出",
                            "quantity": int(ratio),
                            "price": f"${getattr(order, 'limit_price', 0):.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-",
                            "status": self._translate_status(order_status)
                        })
                    
                    # 判断策略类型
                    strategy = self._determine_strategy(legs)
                    
                    processed_order_ids.add(order_id)
                    order_list.append({
                        "order_id": order_id,
                        "strategy": strategy,
                        "direction": "组合",
                        "quantity": int(order.quantity or 0),
                        "order_type": self._translate_order_type(order.order_type if hasattr(order, 'order_type') else ''),
                        "price": f"${order.limit_price:.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-",
                        "status": self._translate_status(order_status),
                        "standard_status": self._get_standard_status(order_status),
                        "time": self._format_time(order_time),
                        "legs": legs
                    })
                else:
                    # 单个订单，尝试通过时间匹配找到可能的组合
                    if contract:
                        symbol = getattr(contract, 'identifier', None) or getattr(contract, 'symbol', '')
                    else:
                        symbol = ''
                    
                    # 解析期权信息
                    try:
                        option_info = parse_option_symbol(symbol)
                        base_symbol = option_info.get('symbol', '')
                        expiry = option_info.get('expiry', '')
                        strike = option_info.get('strike', 0)
                        put_call = option_info.get('put_call', 'CALL')
                    except Exception:
                        base_symbol = symbol.split()[0] if ' ' in symbol else symbol
                        expiry = ''
                        strike = 0
                        put_call = 'CALL'
                    
                    # 查找相同时间（5秒内）、相同标的、相同到期日的其他订单，可能是组合
                    # 限制：最多匹配3个其他订单（总共最多4条腿），且数量要相同
                    matched_orders = []
                    order_quantity = int(order.quantity or 0)
                    
                    for other_raw in raw_orders:
                        if other_raw['order'].id == order.id:
                            continue
                        if str(other_raw['order'].id) in processed_order_ids:
                            continue
                        
                        # 跳过已有 contract_legs 的组合订单（它们已经是完整的组合了）
                        if other_raw['contract_legs'] and len(other_raw['contract_legs']) > 1:
                            continue
                        
                        # 限制组合订单最多4条腿（1个主订单 + 最多3个匹配订单）
                        if len(matched_orders) >= 3:
                            break
                        
                        other_contract = other_raw['contract']
                        other_time = other_raw['order_time']
                        other_order = other_raw['order']
                        
                        # 检查时间是否接近（5秒内）
                        if order_time and other_time:
                            try:
                                time_diff = abs(self._parse_time(order_time) - self._parse_time(other_time))
                                if time_diff > 5:  # 超过5秒，不认为是组合
                                    continue
                            except:
                                pass
                        
                        # 检查数量是否相同（组合订单的腿数量应该相同）
                        other_quantity = int(getattr(other_order, 'quantity', 0) or 0)
                        if order_quantity > 0 and other_quantity != order_quantity:
                            continue
                        
                        # 检查是否是期权订单
                        if other_contract:
                            other_sec_type = getattr(other_contract, 'sec_type', '')
                            if other_sec_type != 'OPT':
                                continue
                            
                            other_symbol = getattr(other_contract, 'identifier', None) or getattr(other_contract, 'symbol', '')
                            try:
                                other_option_info = parse_option_symbol(other_symbol)
                                other_base_symbol = other_option_info.get('symbol', '')
                                other_expiry = other_option_info.get('expiry', '')
                                other_strike = other_option_info.get('strike', 0)
                                other_put_call = other_option_info.get('put_call', 'CALL')
                            except:
                                continue
                            
                            # 检查是否是相同标的、相同到期日、相同类型（CALL或PUT）
                            # 行权价相差不超过50点（更严格，避免误匹配）
                            if (other_base_symbol == base_symbol and 
                                other_expiry == expiry and 
                                other_put_call == put_call and
                                abs(other_strike - strike) <= 50):  # 行权价相差不超过50点
                                matched_orders.append(other_raw)
                    
                    # 如果找到匹配的订单，组成组合（但最多4条腿）
                    if matched_orders and len(matched_orders) <= 3:
                        # 构建组合订单
                        legs = [{
                            "symbol": symbol,
                            "direction": "买入" if (hasattr(order, 'action') and order.action == 'BUY') else "卖出",
                            "quantity": int(order.quantity or 0),
                            "price": f"${order.limit_price:.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-",
                            "status": self._translate_status(order_status)
                        }]
                        
                        for matched_raw in matched_orders:
                            matched_order = matched_raw['order']
                            matched_contract = matched_raw['contract']
                            matched_status = matched_raw['status']
                            
                            matched_symbol = getattr(matched_contract, 'identifier', None) or getattr(matched_contract, 'symbol', '')
                            legs.append({
                                "symbol": matched_symbol,
                                "direction": "买入" if (hasattr(matched_order, 'action') and matched_order.action == 'BUY') else "卖出",
                                "quantity": int(matched_order.quantity or 0),
                                "price": f"${matched_order.limit_price:.2f}" if hasattr(matched_order, 'limit_price') and matched_order.limit_price else "-",
                                "status": self._translate_status(matched_status)
                            })
                            
                            processed_order_ids.add(str(matched_order.id))
                        
                        # 判断策略类型
                        strategy = self._determine_strategy(legs)
                        
                        processed_order_ids.add(order_id)
                        order_list.append({
                            "order_id": order_id,
                            "strategy": strategy,
                            "direction": "组合",
                            "quantity": int(order.quantity or 0),
                            "order_type": self._translate_order_type(order.order_type if hasattr(order, 'order_type') else ''),
                            "price": f"${order.limit_price:.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-",
                            "status": self._translate_status(order_status),
                            "standard_status": self._get_standard_status(order_status),
                            "time": self._format_time(order_time),
                            "legs": legs
                        })
                    else:
                        # 单个订单
                        processed_order_ids.add(order_id)
                        order_list.append({
                            "order_id": order_id,
                            "strategy": "单腿",
                            "direction": "买入" if (hasattr(order, 'action') and order.action == 'BUY') else "卖出",
                            "quantity": int(order.quantity or 0),
                            "order_type": self._translate_order_type(order.order_type if hasattr(order, 'order_type') else ''),
                            "price": f"${order.limit_price:.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-",
                            "status": self._translate_status(order_status),
                            "standard_status": self._get_standard_status(order_status),
                            "time": self._format_time(order_time),
                            "legs": [{
                                "symbol": symbol,
                                "direction": "买入" if (hasattr(order, 'action') and order.action == 'BUY') else "卖出",
                                "quantity": int(order.quantity or 0),
                                "price": f"${order.limit_price:.2f}" if hasattr(order, 'limit_price') and order.limit_price else "-",
                                "status": self._translate_status(order_status)
                            }]
                        })
            
            return order_list
            
        except Exception as e:
            logger.error(f"查询订单列表失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
        return []
    
    def _translate_status(self, status) -> str:
        """翻译订单状态（返回中文显示文本）
        
        使用标准化状态映射，将 Tiger 券商的订单状态转换为标准状态，
        然后返回对应的中文显示文本。
        
        根据 Tiger API 的 OrderStatus 枚举：
        - EXPIRED: 非法状态 (-2)
        - NEW: 订单初始状态 (-1)
        - CANCELLED: 已取消 (4)
        - HELD: 订单已经提交 (5)
        - PARTIALLY_FILLED: 部分成交 (2, 5, 8)
        - FILLED: 完全成交 (6)
        - REJECTED: 已失效 (7)
        """
        # 使用标准化状态映射
        standard_status = map_tiger_status(status)
        status_info = get_status_info(standard_status)
        return status_info.label_cn
    
    def _get_standard_status(self, status) -> str:
        """获取标准化订单状态（用于存储和跨券商统一）
        
        Args:
            status: Tiger 券商的原始订单状态
        
        Returns:
            标准化状态字符串，如 'NEW', 'FILLED', 'CANCELLED' 等
        """
        standard_status = map_tiger_status(status)
        return standard_status.value
    
    def _translate_order_type(self, order_type: str) -> str:
        """翻译订单类型"""
        type_map = {
            'MKT': '市价',
            'LMT': '限价',
            'STP': '止损',
            'STP_LMT': '止损限价'
        }
        return type_map.get(order_type, order_type)
    
    def _format_time(self, timestamp: Optional[Any]) -> str:
        """格式化时间（包含日期，使用美国时间）"""
        if not timestamp:
            return ""
        try:
            # 如果是毫秒时间戳
            if isinstance(timestamp, (int, float)):
                if timestamp > 1e12:  # 毫秒时间戳
                    timestamp = timestamp / 1000
                # 转换为纽约时区
                dt = datetime.fromtimestamp(timestamp, tz=NY_TIMEZONE)
            else:
                # 如果已经是 datetime 对象，确保转换为纽约时区
                if isinstance(timestamp, datetime):
                    if timestamp.tzinfo is None:
                        # 如果没有时区信息，假设是UTC
                        dt = timestamp.replace(tzinfo=ZoneInfo("UTC")).astimezone(NY_TIMEZONE)
                    else:
                        dt = timestamp.astimezone(NY_TIMEZONE)
                else:
                    dt = timestamp
            # 返回包含日期的格式：YYYY-MM-DD HH:MM:SS
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(timestamp)
    
    def _parse_time(self, timestamp) -> float:
        """解析时间戳为浮点数（秒）"""
        if not timestamp:
            return 0
        try:
            # 如果是毫秒时间戳
            if isinstance(timestamp, (int, float)):
                if timestamp > 1e12:  # 毫秒时间戳
                    return timestamp / 1000
                return float(timestamp)
            elif hasattr(timestamp, 'timestamp'):
                return timestamp.timestamp()
            else:
                # 尝试解析字符串
                from datetime import datetime
                if isinstance(timestamp, str):
                    # 尝试多种格式
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                        try:
                            dt = datetime.strptime(timestamp, fmt)
                            return dt.timestamp()
                        except:
                            continue
                return 0
        except Exception:
            return 0
    
    def _determine_strategy(self, legs: List[Dict[str, Any]]) -> str:
        """根据腿判断策略类型"""
        if len(legs) == 2:
            directions = [leg.get('direction', '') for leg in legs]
            if '买入' in directions and '卖出' in directions:
                # 检查是否是同类型期权 - 统一使用"垂直价差"
                symbols = [leg.get('symbol', '') for leg in legs]
                if all('C' in s or 'CALL' in s for s in symbols):
                    return "垂直价差"
                elif all('P' in s or 'PUT' in s for s in symbols):
                    return "垂直价差"
                else:
                    return "价差"
            else:
                return "跨式"
        elif len(legs) == 3:
            return "蝶式"
        elif len(legs) == 4:
            return "铁鹰"
        else:
            return "组合"
    
    def supports_combined_order(self) -> bool:
        """是否支持组合下单"""
        return True  # 老虎证券支持组合下单

    @staticmethod
    def _infer_combo_type(option_infos: List[Dict[str, Any]]) -> Any:
        """按腿结构选择老虎 ComboType（见官方「下单交易」文档）。"""
        if ComboType is None or len(option_infos) != 2:
            return ComboType.CUSTOM if ComboType else "CUSTOM"
        a, b = option_infos[0], option_infos[1]
        und_a = (a.get("underlying") or a.get("symbol") or "").upper()
        und_b = (b.get("underlying") or b.get("symbol") or "").upper()
        if und_a != und_b:
            return ComboType.CUSTOM
        same_expiry = a.get("expiry_contract") == b.get("expiry_contract")
        same_strike = float(a.get("strike") or 0) == float(b.get("strike") or 0)
        same_pc = (a.get("put_call") or "").upper() == (b.get("put_call") or "").upper()
        if same_expiry and not same_strike and same_pc:
            return ComboType.VERTICAL
        if (not same_expiry) and same_strike and same_pc:
            return ComboType.CALENDAR
        if same_expiry and same_strike and not same_pc:
            return ComboType.STRADDLE
        if same_expiry and (not same_strike) and (not same_pc):
            return ComboType.STRANGLE
        return ComboType.CUSTOM

    @staticmethod
    def _is_credit_combo(signal: Signal, option_infos: List[Dict[str, Any]]) -> bool:
        """收入型组合（PCS/垂直信用价差）：老虎 LMT 限价须为负（对齐 spx/online combo_lmt）。"""
        meta = signal.metadata or {}
        nested = meta.get("sunnyquant") if isinstance(meta.get("sunnyquant"), dict) else {}
        for key in ("combo", "strategy_family", "order_combo"):
            val = str(meta.get(key) or nested.get(key) or "").lower()
            if "credit" in val:
                return True
        legs = signal.legs or []
        if len(legs) != 2 or len(option_infos) != 2:
            return False
        by_action: Dict[str, Dict[str, Any]] = {}
        for leg, info in zip(legs, option_infos):
            by_action[(leg.action or "").upper()] = info
        sell = by_action.get("SELL")
        buy = by_action.get("BUY")
        if not sell or not buy:
            return False
        if (sell.get("put_call") or "").upper() != (buy.get("put_call") or "").upper():
            return False
        if sell.get("expiry_contract") != buy.get("expiry_contract"):
            return False
        # 卖高买低（put credit）或卖低买高（call credit）
        return float(sell.get("strike") or 0) != float(buy.get("strike") or 0)

    @classmethod
    def _combo_limit_price(
        cls,
        signal: Signal,
        order_type: str,
        option_infos: List[Dict[str, Any]],
    ) -> Optional[float]:
        if signal.limit_price is None:
            return None
        px = float(signal.limit_price)
        # 收入型：无论上层传 LMT/MKT，只要有净权利金就按负数限价走 LMT（见下方 coerce）
        if cls._is_credit_combo(signal, option_infos):
            return -abs(px)
        if order_type != "LMT":
            return None
        return px
    
    def get_account_display_info(self) -> Dict[str, Any]:
        """
        获取账户显示信息（用于在界面上显示）
        
        Returns:
            {
                "account": "账户ID",
                "tiger_id": "Tiger ID",
                "env": "test" 或 "production",
                "env_display": "测试环境" 或 "正式环境"
            }
        """
        env_display = "正式环境" if self.env == "production" else "测试环境"
        return {
            "account": self.account or "N/A",
            "tiger_id": self.tiger_id or "N/A",
            "env": self.env,
            "env_display": env_display
        }
