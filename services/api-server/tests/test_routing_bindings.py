"""券商绑定匹配：account_id 优先，不依赖 label / 推送邮箱。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api-server"))

from app.services.routing import select_bindings_for_rule  # noqa: E402


def _binding(**kwargs):
    return SimpleNamespace(
        broker=kwargs.get("broker", "tiger"),
        account_id=kwargs.get("account_id", ""),
        label=kwargs.get("label", ""),
        device_id=None,
        order_type_policy="LMT_then_MKT",
    )


def _rule(**kwargs):
    return SimpleNamespace(
        broker=kwargs.get("broker", "tiger"),
        account_id=kwargs.get("account_id"),
        account_label=kwargs.get("account_label"),
        order_type_policy="MKT_only",
        action="auto_trade",
    )


def test_match_by_account_id_even_if_label_drifted():
    bindings = [
        _binding(account_id="21259600801814618", label="老虎测试1"),
    ]
    rule = _rule(account_id="21259600801814618", account_label="老虎测试2")
    routed, blocked = select_bindings_for_rule(bindings, rule)
    assert blocked is None
    assert len(routed) == 1
    assert routed[0].account_id == "21259600801814618"


def test_label_only_when_no_account_id():
    bindings = [
        _binding(account_id="aaa", label="纸面A"),
        _binding(account_id="bbb", label="纸面B"),
    ]
    rule = _rule(account_id=None, account_label="纸面B")
    routed, blocked = select_bindings_for_rule(bindings, rule)
    assert blocked is None
    assert [b.account_id for b in routed] == ["bbb"]


def test_wrong_account_id_blocks():
    bindings = [_binding(account_id="aaa", label="x")]
    rule = _rule(account_id="zzz", account_label="x")
    routed, blocked = select_bindings_for_rule(bindings, rule)
    assert routed == []
    assert blocked == "broker_binding_mismatch"


def test_no_rule_broker_returns_all():
    bindings = [_binding(broker="ibkr"), _binding(broker="tiger")]
    routed, blocked = select_bindings_for_rule(bindings, None)
    assert blocked is None
    assert len(routed) == 2
