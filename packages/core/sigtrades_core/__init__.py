"""sigtrades_core: 跨云端/Agent 共享的核心包。

包含：
- signal.models   : 统一信号领域模型（vendored from sigx，无 Qt 依赖）
- brokers.*        : 券商适配器（Tiger 云端 / IBKR / 富途）
- trading.order_status : 跨券商标准化订单状态
- execution.core  : 去 Qt 的执行状态机（下单/查单/重试/撤单重下）
- sources.*       : 信号源统一标准接口（BaseSignalSource）
"""

__version__ = "0.1.0"
