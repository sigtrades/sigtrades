"""Account probe summary normalization."""

from sigtrades_core.brokers.account_probe import normalize_account_summary


def test_normalize_tiger():
    s = normalize_account_summary(
        "tiger",
        {
            "account_id": "21259600801814618",
            "net_liquidation": 100.0,
            "available_cash": 90.0,
            "is_paper": True,
        },
    )
    assert s["available_cash"] == 90.0
    assert s["is_paper"] is True


def test_normalize_alpaca():
    s = normalize_account_summary(
        "alpaca",
        {"account_number": "PA123", "equity": "50.5", "cash": "40", "currency": "USD"},
    )
    assert s["net_liquidation"] == 50.5
    assert s["available_cash"] == 40.0


def test_normalize_longbridge():
    s = normalize_account_summary(
        "longbridge",
        {
            "env": "sandbox",
            "balances": [{"currency": "USD", "net_assets": 12, "total_cash": 10}],
        },
    )
    assert s["net_liquidation"] == 12.0
    assert s["is_paper"] is True
