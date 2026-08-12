"""邮件确认 token 签发/解析。"""

from __future__ import annotations

import uuid

from app.services.confirm_trade_service import issue_action_token
from app.security import decode_state_token


def test_issue_and_decode_confirm_token():
    uid = uuid.uuid4()
    token = issue_action_token(
        user_id=uid,
        signal_id="sig-1",
        source_id="src-1",
        action="confirm",
        account_label="IBKR Paper",
        broker="ibkr",
        account_id="DU123",
    )
    payload = decode_state_token(token)
    assert payload is not None
    assert payload["purpose"] == "confirm_action"
    assert payload["act"] == "confirm"
    assert payload["uid"] == str(uid)
    assert payload["sid"] == "sig-1"
    assert payload["src"] == "src-1"
    assert payload["al"] == "IBKR Paper"
    assert payload["jti"]


def test_reject_token_action():
    token = issue_action_token(
        user_id=uuid.uuid4(),
        signal_id="s",
        source_id="src",
        action="reject",
    )
    payload = decode_state_token(token)
    assert payload is not None
    assert payload["act"] == "reject"
