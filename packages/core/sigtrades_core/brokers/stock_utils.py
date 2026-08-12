"""判断是否为股票现货信号。"""

from __future__ import annotations

from sigtrades_core.signal.models import Signal, AssetClass


def is_stock_signal(signal: Signal) -> bool:
    if signal.asset_class == AssetClass.STOCK.value or signal.asset_class == "STOCK":
        return True
    if signal.legs:
        return False
    sym = (signal.symbol or "").strip()
    if not sym:
        return False
    # 期权代码通常含空格+到期日行权价
    if " " in sym:
        return False
    return len(sym) <= 6 and sym.isalpha()
