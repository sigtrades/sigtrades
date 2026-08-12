"""uSMART Open API RSA helpers (MD5withRSA sign + PKCS1v1.5 encrypt).

官方文档：https://api-doc.usmart.sg/zh-cn/trade.html
- X-Sign：对 Body 做 MD5withRSA，再 URL-safe Base64
- 手机号/密码：RSA 公钥加密后 URL-safe Base64
"""

from __future__ import annotations

import base64
import random
import re
import time
from typing import Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

KeyLike = Union[str, bytes]


def _normalize_pem(raw: str, *, kind: str) -> bytes:
    text = (raw or "").strip().replace("\\n", "\n")
    if "BEGIN" in text:
        return text.encode("utf-8")
    # 去掉空白后按 64 列重排裸 base64
    body = re.sub(r"\s+", "", text)
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    joined = "\n".join(lines)
    if kind == "public":
        pem = f"-----BEGIN PUBLIC KEY-----\n{joined}\n-----END PUBLIC KEY-----\n"
    else:
        # 兼容 PKCS#1 / PKCS#8 裸钥：先试 PRIVATE KEY，再由 loader 报错
        pem = f"-----BEGIN PRIVATE KEY-----\n{joined}\n-----END PRIVATE KEY-----\n"
    return pem.encode("utf-8")


def load_public_key(raw: KeyLike) -> RSAPublicKey:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    text = data.decode("utf-8", errors="ignore")
    candidates = [data]
    if "BEGIN" not in text:
        candidates.append(_normalize_pem(text, kind="public"))
        # 部分渠道下发 PKCS#1 PUBLIC KEY
        body = re.sub(r"\s+", "", text)
        lines = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
        candidates.append(
            f"-----BEGIN RSA PUBLIC KEY-----\n{lines}\n-----END RSA PUBLIC KEY-----\n".encode()
        )
    last_err: Exception | None = None
    for blob in candidates:
        try:
            key = serialization.load_pem_public_key(blob)
            if isinstance(key, RSAPublicKey):
                return key
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise ValueError(f"无法解析 uSMART 公钥: {last_err}")


def load_private_key(raw: KeyLike) -> RSAPrivateKey:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    text = data.decode("utf-8", errors="ignore")
    candidates = [data]
    if "BEGIN" not in text:
        body = re.sub(r"\s+", "", text)
        lines = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
        candidates.append(
            f"-----BEGIN PRIVATE KEY-----\n{lines}\n-----END PRIVATE KEY-----\n".encode()
        )
        candidates.append(
            f"-----BEGIN RSA PRIVATE KEY-----\n{lines}\n-----END RSA PRIVATE KEY-----\n".encode()
        )
    last_err: Exception | None = None
    for blob in candidates:
        try:
            key = serialization.load_pem_private_key(blob, password=None)
            if isinstance(key, RSAPrivateKey):
                return key
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise ValueError(f"无法解析 uSMART 私钥: {last_err}")


def rsa_encrypt_urlsafe(public_key: RSAPublicKey, plaintext: str) -> str:
    cipher = public_key.encrypt(plaintext.encode("utf-8"), padding.PKCS1v15())
    return base64.urlsafe_b64encode(cipher).decode("ascii")


def sign_md5_with_rsa_urlsafe(private_key: RSAPrivateKey, content: str) -> str:
    signature = private_key.sign(
        content.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.MD5(),
    )
    return base64.urlsafe_b64encode(signature).decode("ascii")


def sign_md5_with_rsa_b64(private_key: RSAPrivateKey, content: str) -> str:
    """交易接口 X-Sign：MD5withRSA + 标准 Base64（与官方 openapi-sg-demo-py 一致）。"""
    signature = private_key.sign(
        content.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.MD5(),
    )
    return base64.b64encode(signature).decode("ascii")


def gen_request_id(length: int = 19) -> str:
    """生成 19 位数字请求 ID（幂等防重）。"""
    time_part = str(int(time.time() * 1_000_000))
    random_part = f"{random.randint(0, 999):03d}"
    return (time_part + random_part)[:length].ljust(length, "0")


def gen_unix_time(length: int = 10) -> str:
    """与官方 demo gen_unix_time_str 一致：默认 10 位秒级；16 位为微秒扩展。"""
    if length <= 10:
        return str(int(time.time()))[:length]
    return str(int(time.time() * 10 ** (length - 10)))
