"""老虎密钥应用层加解密（Fernet 对称加密）。

凭证以密文存于云端 DB；cloud-executor 在运行时取出密文并用 FERNET_KEY 解密，
解密后的私钥仅存在于内存，用完即弃。
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    if not settings.FERNET_KEY:
        raise RuntimeError("FERNET_KEY 未配置，无法解密券商凭证")
    return Fernet(settings.FERNET_KEY.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
