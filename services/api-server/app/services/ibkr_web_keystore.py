"""一键生成 IBKR First Party OAuth 材料（不落库，仅返回一次）。"""

from __future__ import annotations

from typing import Dict

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dh, rsa


def generate_ibkr_oauth_materials() -> Dict[str, str]:
    """生成签名/加密 RSA 密钥对与 DH 参数。

    返回字段与控制台表单、IBKR 上传页对齐：
    - private_* / dhparam：填入 SigTrades
    - public_* / dhparam：上传 IBKR
    """
    sig = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    enc = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    dh_params = dh.generate_parameters(generator=2, key_size=2048)

    def _priv_pem(key: rsa.RSAPrivateKey) -> str:
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    def _pub_pem(key: rsa.RSAPrivateKey) -> str:
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    dhparam_pem = dh_params.parameter_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.ParameterFormat.PKCS3,
    ).decode("utf-8")

    return {
        "signature_key_pem": _priv_pem(sig),
        "encryption_key_pem": _priv_pem(enc),
        "public_signature_pem": _pub_pem(sig),
        "public_encryption_pem": _pub_pem(enc),
        "dhparam_pem": dhparam_pem,
    }
