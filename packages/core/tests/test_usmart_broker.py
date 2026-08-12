"""uSMART adapter unit tests (no live API)."""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sigtrades_core.brokers import BROKER_DEPLOYMENT, create_broker_adapter, deployment_for
from sigtrades_core.brokers.status_mapping import UsmartStatusMapper
from sigtrades_core.brokers.usmart.crypto import (
    gen_unix_time,
    load_private_key,
    load_public_key,
    rsa_encrypt_urlsafe,
    sign_md5_with_rsa_b64,
    sign_md5_with_rsa_urlsafe,
)
from sigtrades_core.trading.order_status import OrderStatus


def test_usmart_is_cloud_deployment():
    assert BROKER_DEPLOYMENT["usmart"] == "cloud"
    assert deployment_for("usmart") == "cloud"


def test_create_usmart_adapter_aliases():
    cfg = {
        "channel": "1001",
        "public_key": "placeholder",
        "private_key": "placeholder",
        "region": "sg",
    }
    adapter = create_broker_adapter("usmart", cfg)
    assert adapter.__class__.__name__ == "UsmartBrokerAdapter"
    assert adapter.trade_host == "https://open-jy.usmartsg.com"
    adapter2 = create_broker_adapter("盈立证券", cfg)
    assert adapter2.__class__.__name__ == "UsmartBrokerAdapter"


def test_usmart_connect_requires_login_secrets():
    cfg = {
        "channel": "1001",
        "public_key": "placeholder",
        "private_key": "placeholder",
    }
    adapter = create_broker_adapter("usmart", cfg)
    assert adapter.connect() is False
    assert "手机号" in (adapter.connect_error or "")


def test_usmart_status_mapper():
    assert UsmartStatusMapper.to_standard("已成") == OrderStatus.FILLED
    assert UsmartStatusMapper.to_standard("已撤") == OrderStatus.CANCELLED
    assert UsmartStatusMapper.to_standard(8) == OrderStatus.FILLED
    assert UsmartStatusMapper.to_standard("等待提交") == OrderStatus.PENDING


def test_usmart_crypto_roundtrip_sign_encrypt():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    pub = load_public_key(public_pem)
    priv = load_private_key(private_pem)
    cipher = rsa_encrypt_urlsafe(pub, "hello-usmart")
    assert isinstance(cipher, str) and len(cipher) > 20
    sign = sign_md5_with_rsa_urlsafe(priv, '{"a":1}')
    assert isinstance(sign, str) and len(sign) > 20
    sign_b64 = sign_md5_with_rsa_b64(priv, '{"a": 1}')
    assert isinstance(sign_b64, str) and len(sign_b64) > 20
    assert len(gen_unix_time(16)) >= 16
