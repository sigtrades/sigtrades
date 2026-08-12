"""期权符号适配器测试。"""

from __future__ import annotations

import pytest

from sigtrades_core.signal.models import Signal
from sigtrades_core.signal.option_symbol import (
    apply_source_option_dte,
    expiry_from_dte,
    format_broker_option_symbol,
    format_futu_option_code,
    format_longbridge_option_symbol,
    format_longbridge_stock_symbol,
    format_tiger_option_identifier,
    normalize_option_signal,
    parse_option_symbol,
    ParsedOption,
)


def test_parse_short_spy_758c_defaults_today():
    info = parse_option_symbol("SPY 758C")
    assert info["underlying"] == "SPY"
    assert info["strike"] == 758.0
    assert info["right"] == "C"
    assert info["put_call"] == "CALL"
    assert len(info["expiry_contract"]) == 8


def test_parse_full_format():
    info = parse_option_symbol("SPY 240119C450")
    assert info["underlying"] == "SPY"
    assert info["strike"] == 450.0
    assert info["expiry_contract"] == "20240119"
    assert info["right"] == "C"


def test_parse_occ_compact_spxw():
    info = parse_option_symbol("SPXW250721P07450000")
    assert info["underlying"] == "SPXW"
    assert info["strike"] == 7450.0
    assert info["expiry_contract"] == "20250721"
    assert info["right"] == "P"
    assert info["put_call"] == "PUT"


def test_parse_occ_compact_aapl():
    info = parse_option_symbol("AAPL250117P00200000")
    assert info["underlying"] == "AAPL"
    assert info["strike"] == 200.0
    assert info["expiry_contract"] == "20250117"
    assert info["right"] == "P"


def test_parse_from_metadata_only():
    info = parse_option_symbol(
        "",
        metadata={"underlying": "SPY", "strike": 758, "right": "C", "expiry": "20260607"},
    )
    assert info["underlying"] == "SPY"
    assert info["strike"] == 758.0
    assert info["expiry_contract"] == "20260607"


def test_normalize_short_symbol_to_broker_format():
    signal = Signal.from_dict({
        "signal_id": "t1",
        "timestamp": 1.0,
        "action": "BUY",
        "symbol": "SPY 758C",
        "quantity": 1,
        "asset_class": "OPTIONS",
        "metadata": {"underlying": "SPY", "strike": 758, "right": "C"},
    })
    normalized = normalize_option_signal(signal)
    assert normalized.legs is not None
    assert len(normalized.legs) == 1
    # 应转为 SPY YYMMDD C 8位行权价 格式
    assert normalized.symbol.startswith("SPY ")
    assert "C00758000" in normalized.symbol.replace(" ", "")


def test_format_futu_code():
    parsed = ParsedOption(
        underlying="SPY",
        strike=758.0,
        right="C",
        put_call="CALL",
        expiry="2026-06-07",
        expiry_contract="20260607",
    )
    code = format_futu_option_code(parsed)
    # 股票/ETF：单点 + 行权价不补零（对齐官方 US.NVDA260330C160000）
    assert code == "US.SPY260607C758000"


def test_format_futu_index_option_single_dot():
    """指数期权用 US. 单点；US..SPXW... 会被 OpenD 判为未知股票。"""
    parsed = ParsedOption(
        underlying="SPXW",
        strike=7370.0,
        right="P",
        put_call="PUT",
        expiry="2026-07-29",
        expiry_contract="20260729",
    )
    assert format_futu_option_code(parsed) == "US.SPXW260729P7370000"


def test_invalid_symbol_raises():
    with pytest.raises(ValueError, match="无效的期权代码格式"):
        parse_option_symbol("INVALID")


def test_expiry_from_dte_offsets_days():
    today = expiry_from_dte(0)
    tomorrow = expiry_from_dte(1)
    assert today[1] != tomorrow[1] or today[0] != tomorrow[0]


def test_apply_source_option_dte_writes_metadata():
    signal = {
        "symbol": "SPY 758C",
        "asset_class": "OPTIONS",
        "metadata": {"underlying": "SPY", "strike": 758, "right": "C"},
    }
    out = apply_source_option_dte(signal, 1)
    assert out["metadata"]["dte"] == 1
    assert out["metadata"]["expiry"]
    assert out["metadata"]["expiry_contract"]


def test_apply_source_option_dte_skips_when_expiry_present():
    signal = {
        "symbol": "SPY 758C",
        "asset_class": "OPTIONS",
        "metadata": {"underlying": "SPY", "strike": 758, "right": "C", "expiry": "2026-06-07"},
    }
    out = apply_source_option_dte(signal, 1)
    assert out["metadata"]["expiry"] == "2026-06-07"
    assert "dte" not in out["metadata"]


def test_parse_option_symbol_uses_metadata_dte():
    info = parse_option_symbol(
        "SPY 758C",
        metadata={"underlying": "SPY", "strike": 758, "right": "C", "dte": 1},
    )
    expected = expiry_from_dte(1)
    assert info["expiry"] == expected[0]
    assert info["expiry_contract"] == expected[1]


def test_format_broker_decimal_strike():
    parsed = ParsedOption(
        underlying="AAPL",
        strike=297.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-26",
        expiry_contract="20260626",
    )
    sym = format_broker_option_symbol(parsed)
    assert sym == "AAPL 260626C00297500"
    info = parse_option_symbol(sym)
    assert info["strike"] == 297.5
    assert info["expiry_contract"] == "20260626"


def test_normalize_aapl_decimal_strike():
    signal = Signal.from_dict({
        "signal_id": "t2",
        "timestamp": 1.0,
        "action": "BUY",
        "symbol": "AAPL 297.5C",
        "quantity": 1,
        "asset_class": "OPTIONS",
        "metadata": {
            "underlying": "AAPL",
            "strike": 297.5,
            "right": "C",
            "expiry": "2026-06-26",
        },
    })
    normalized = normalize_option_signal(signal)
    assert normalized.symbol == "AAPL 260626C00297500"
    info = parse_option_symbol(normalized.symbol)
    assert info["strike"] == 297.5


def test_normalize_skips_explicit_stock():
    signal = Signal.from_dict({
        "signal_id": "t-stock",
        "timestamp": 1.0,
        "action": "BUY",
        "symbol": "SPY",
        "quantity": 100,
        "limit_price": 735.50,
        "asset_class": "STOCK",
    })
    normalized = normalize_option_signal(signal)
    assert normalized.symbol == "SPY"
    assert not normalized.legs
    assert normalized.asset_class == "STOCK"


def test_format_longbridge_option_decimal_strike():
    parsed = ParsedOption(
        underlying="AAPL",
        strike=297.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-26",
        expiry_contract="20260626",
    )
    assert format_longbridge_option_symbol(parsed) == "AAPL260626C297500.US"


def test_format_longbridge_option_low_strike_no_leading_zeros():
    """长桥行权价不补前导零：$27.50 → 27500，非老虎 OCC 的 00275000。"""
    parsed = ParsedOption(
        underlying="CIFR",
        strike=27.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-18",
        expiry_contract="20260618",
    )
    assert format_longbridge_option_symbol(parsed) == "CIFR260618C27500.US"


def test_format_longbridge_differs_from_tiger_eight_digit_strike():
    parsed = ParsedOption(
        underlying="CIFR",
        strike=27.5,
        right="C",
        put_call="CALL",
        expiry="2026-06-18",
        expiry_contract="20260618",
    )
    tiger_style = format_broker_option_symbol(parsed)
    lb_style = format_longbridge_option_symbol(parsed)
    assert "00027500" in tiger_style.replace(" ", "")
    assert "00027500" not in lb_style
    assert lb_style == "CIFR260618C27500.US"


def test_format_longbridge_stock_symbol():
    assert format_longbridge_stock_symbol("aapl") == "AAPL.US"
    assert format_longbridge_stock_symbol("TSLA.US") == "TSLA.US"


def test_format_tiger_option_identifier_pads_underlying():
    parsed = ParsedOption(
        underlying="SPY",
        strike=680.0,
        right="P",
        put_call="PUT",
        expiry="2026-07-24",
        expiry_contract="20260724",
    )
    assert format_tiger_option_identifier(parsed) == "SPY   260724P00680000"
    assert len(format_tiger_option_identifier(parsed)) == 21
