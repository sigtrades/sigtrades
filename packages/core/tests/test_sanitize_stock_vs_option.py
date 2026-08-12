"""正股被误标为期权时的纠正。"""

from __future__ import annotations

from sigtrades_core.parse.parser import parse_heuristic, sanitize_stock_vs_option


def test_sanitize_plain_ticker_to_stock():
    out = sanitize_stock_vs_option(
        {"symbol": "SPY", "asset_class": "OPTIONS", "quantity": 100, "limit_price": 735.5}
    )
    assert out["asset_class"] == "STOCK"
    assert out["symbol"] == "SPY"


def test_sanitize_stock_price_mistaken_as_strike():
    out = sanitize_stock_vs_option(
        {
            "symbol": "SPY 735C",
            "asset_class": "OPTIONS",
            "quantity": 1,
            "limit_price": 735.50,
            "metadata": {
                "raw_text": "BUY SPY 100 @735.50",
                "underlying": "SPY",
                "strike": 735,
                "right": "C",
            },
        }
    )
    assert out["asset_class"] == "STOCK"
    assert out["symbol"] == "SPY"
    assert out["quantity"] == 100
    assert out["metadata"].get("strike") is None
    assert out["metadata"].get("right") is None


def test_sanitize_keeps_real_option_premium():
    out = sanitize_stock_vs_option(
        {
            "symbol": "SPY 735C",
            "asset_class": "OPTIONS",
            "quantity": 1,
            "limit_price": 2.45,
            "metadata": {"underlying": "SPY", "strike": 735, "right": "C"},
        }
    )
    assert out["asset_class"] == "OPTIONS"
    assert out["symbol"] == "SPY 735C"


def test_heuristic_buy_stock_qty_at_price():
    r = parse_heuristic("BUY SPY 100 @735.50")
    assert r.signal["asset_class"] == "STOCK"
    assert r.signal["symbol"] == "SPY"
    assert r.signal["quantity"] == 100
    assert r.signal["limit_price"] == 735.50
