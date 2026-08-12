"""老虎私钥 Fernet 加解密（与 cloud-executor 共用 FERNET_KEY）。"""

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    if not settings.FERNET_KEY:
        raise RuntimeError("FERNET_KEY 未配置")
    return Fernet(settings.FERNET_KEY.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
