"""样例规则生成器测试。"""

from __future__ import annotations

import pytest

from sigtrades_core.parse.rule_generator import generate_parse_rule_from_example
from sigtrades_core.parse.parser import parse_example


AVTR_SAMPLE = """AVTR 10 C 2026-06-18
$284K AVG$0.39 10DTE"""

AVTR_EXPECTED = {
    "action": "BUY",
    "symbol": "AVTR 10C",
    "quantity": 1,
    "limit_price": 0.39,
    "order_type": "LMT",
    "signal_subtype": "OPEN",
    "asset_class": "OPTIONS",
    "metadata": {
        "underlying": "AVTR",
        "strike": 10,
        "right": "C",
        "expiry": "2026-06-18",
        "dte": 10,
    },
}


def test_generate_avtr_flow_alert_rule():
    config = generate_parse_rule_from_example(AVTR_SAMPLE, AVTR_EXPECTED)
    result = parse_example(AVTR_SAMPLE, config)
    assert result.error is None
    assert result.confidence >= 0.9
    assert result.signal["action"] == "BUY"
    assert result.signal["symbol"] == "AVTR 10C"
    assert result.signal["limit_price"] == 0.39
    meta = result.signal["metadata"]
    assert meta["underlying"] == "AVTR"
    assert meta["strike"] == 10.0
    assert meta["expiry"] == "2026-06-18"
    assert meta["dte"] == 10


def test_generate_requires_sample():
    with pytest.raises(ValueError, match="sample is required"):
        generate_parse_rule_from_example("", AVTR_EXPECTED)


def test_flow_alert_rule_matches_different_premium_size():
    config = generate_parse_rule_from_example(AVTR_SAMPLE, AVTR_EXPECTED)
    assert r"$[\d.]+[KMB]" in config["pattern"]
    other = "GLXY 33 C 2026-07-24\n$415K AVG$4.12 46DTE"
    result = parse_example(other, config)
    assert result.error is None
    assert result.confidence >= 0.9
    assert result.signal["symbol"] == "GLXY 33C"
    assert result.signal["metadata"]["underlying"] == "GLXY"


def test_flow_alert_rule_matches_million_premium():
    config = generate_parse_rule_from_example(AVTR_SAMPLE, AVTR_EXPECTED)
    sample = "IREN 50 P 2026-10-16\n$2.7M AVG$10.35 130DTE"
    result = parse_example(sample, config)
    assert result.error is None
    assert result.confidence >= 0.9
    assert result.signal["symbol"] == "IREN 50P"


def test_flow_alert_uses_position_template_not_literal_ticker():
    sample = """TEAM 80 P 2026-08-21
$357K AVG$6.10 74DTE
Informational purposes only. Not financial advice."""
    expected = {
        **AVTR_EXPECTED,
        "symbol": "TEAM 80P",
        "limit_price": 6.10,
        "metadata": {
            "underlying": "TEAM",
            "strike": 80,
            "right": "P",
            "expiry": "2026-08-21",
            "dte": 74,
        },
    }
    config = generate_parse_rule_from_example(sample, expected)
    assert "Informational" not in config["pattern"]
    assert "TEAM" not in config["pattern"]

    cases = [
        ("FDX 340 C 2026-07-02\n$126K AVG$11.79 24DTE", "FDX 340C", 11.79, 24),
        ("WMT 120 P 2026-06-12\n$301K AVG$1.64 4DTE", "WMT 120P", 1.64, 4),
        ("NOK 15 C 2026-06-12\n$683K AVG$0.50 4DTE", "NOK 15C", 0.50, 4),
        ("AMD 500 C 2026-06-12\n$9.1M AVG$13.00 4DTE", "AMD 500C", 13.00, 4),
    ]
    for text, symbol, limit_price, dte in cases:
        result = parse_example(text, config)
        assert result.error is None, text
        assert result.confidence >= 0.9
        assert result.signal["symbol"] == symbol
        assert result.signal["limit_price"] == limit_price
        assert result.signal["metadata"]["dte"] == dte


def test_flow_alert_multi_block_parses_first_signal():
    config = generate_parse_rule_from_example(AVTR_SAMPLE, AVTR_EXPECTED)
    multi = """FDX 340 C 2026-07-02
$126K AVG$11.79 24DTE
Informational purposes only. Not financial advice.
WMT 120 P 2026-06-12
$301K AVG$1.64 4DTE
Informational purposes only. Not financial advice."""
    result = parse_example(multi, config)
    assert result.signal["symbol"] == "FDX 340C"


def test_generate_spy_stock_rule_captures_price_and_qty():
    sample = "BUY SPY 100 @735.50"
    expected = {
        "action": "BUY",
        "symbol": "SPY",
        "quantity": 100,
        "order_type": "LMT",
        "signal_subtype": "OPEN",
        "asset_class": "STOCK",
        "limit_price": 735.50,
    }
    config = generate_parse_rule_from_example(sample, expected)
    assert "@(" in config["pattern"] and "[\\d.]+)" in config["pattern"]
    assert "735.50" not in config["pattern"]
    result = parse_example(sample, config)
    assert result.error is None
    assert result.signal["asset_class"] == "STOCK"
    assert result.signal["symbol"] == "SPY"
    assert result.signal["quantity"] == 100
    assert result.signal["limit_price"] == 735.50

    other = parse_example("BUY AAPL 50 @190.25", config)
    assert other.error is None
    assert other.signal["symbol"] == "AAPL"
    assert other.signal["quantity"] == 50
    assert other.signal["limit_price"] == 190.25
    assert other.signal["asset_class"] == "STOCK"
