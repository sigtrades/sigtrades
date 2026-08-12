"""ibkr_web 工厂与最小适配器行为。"""

from __future__ import annotations

from sigtrades_core.brokers import BROKER_DEPLOYMENT, create_broker_adapter, deployment_for
from sigtrades_core.brokers.ibkr_web.oauth import _k_to_bytes, _parse_dh_prime


def test_ibkr_web_is_cloud_deployment():
    assert BROKER_DEPLOYMENT["ibkr_web"] == "cloud"
    assert deployment_for("ibkr_web") == "cloud"
    assert deployment_for("ibkr") == "gateway"


def test_create_ibkr_web_adapter_incomplete_connect():
    adapter = create_broker_adapter(
        "ibkr_web",
        {
            "account_id": "DU123",
            "env": "paper",
            # 故意缺密钥 → connect 失败但不抛未导入错误
        },
    )
    assert adapter.supports_combined_order() is False
    assert adapter.connect() is False
    assert adapter.connect_error


def test_parse_dh_prime_hex():
    assert _parse_dh_prime("ff") == 255
    assert _parse_dh_prime("0x10") == 16


def test_k_to_bytes_even_hex():
    raw = _k_to_bytes(1)
    assert isinstance(raw, (bytes, bytearray))
    assert len(raw) >= 1
