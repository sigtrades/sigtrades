"""IBKR Web API First Party OAuth 1.0a（Self-Service → Live Session Token）。

流程对齐官方 OAuth 1.0a Extended：跳过 request_token / authorize，
直接用 Self-Service 的 access_token 换 LST，再用 LST 签业务请求。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import quote, quote_plus, urlencode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.ibkr.com/v1/api"
DEFAULT_DH_GENERATOR = 2


def _rfc3986(value: str) -> str:
    return quote(str(value), safe="~")


def _load_rsa_private_key(pem: str) -> RSAPrivateKey:
    text = (pem or "").strip()
    if "BEGIN" not in text:
        # 允许粘贴纯 base64 DER
        try:
            raw = base64.b64decode(text)
            return serialization.load_der_private_key(raw, password=None)  # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"无法解析 RSA 私钥: {exc}") from exc
    key = serialization.load_pem_private_key(text.encode("utf-8"), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("签名/加密密钥必须是 RSA 私钥")
    return key


def _parse_dh_prime(raw: str) -> int:
    text = (raw or "").strip()
    if not text:
        raise ValueError("缺少 dh_prime")
    if text.startswith("-----"):
        # 兼容粘贴 dhparam.pem：取 modulus
        from cryptography.hazmat.primitives.serialization import load_pem_parameters

        params = load_pem_parameters(text.encode("utf-8"))
        numbers = params.parameter_numbers()  # type: ignore[attr-defined]
        return int(numbers.p)
    hex_text = text.lower().removeprefix("0x").replace(" ", "").replace("\n", "")
    return int(hex_text, 16)


def _k_to_bytes(k: int) -> bytes:
    hex_str_k = hex(k)[2:]
    if len(hex_str_k) % 2:
        hex_str_k = "0" + hex_str_k
    raw = bytes.fromhex(hex_str_k)
    if len(bin(k)[2:]) % 8 == 0:
        raw = b"\x00" + raw
    return raw


@dataclass
class IbkrWebSession:
    live_session_token: str
    expires_at_ms: int
    api_cookie: Optional[str] = None

    def is_fresh(self, skew_ms: int = 60_000) -> bool:
        return time.time() * 1000 < (self.expires_at_ms - skew_ms)


class IbkrWebOAuth:
    """管理 LST 与带签名的 HTTP 请求头。"""

    def __init__(self, config: Dict[str, Any]):
        self.consumer_key = (config.get("consumer_key") or "").strip()
        self.access_token = (config.get("access_token") or "").strip()
        self.access_token_secret = (config.get("access_token_secret") or "").strip()
        self._signature_pem = (
            config.get("signature_key_pem") or config.get("signature_key") or ""
        )
        self._encryption_pem = (
            config.get("encryption_key_pem") or config.get("encryption_key") or ""
        )
        self._dh_prime_raw = str(config.get("dh_prime") or "")
        self.signature_key: Optional[RSAPrivateKey] = None
        self.encryption_key: Optional[RSAPrivateKey] = None
        self.dh_prime: Optional[int] = None
        self.dh_generator = int(config.get("dh_generator") or DEFAULT_DH_GENERATOR)
        consumer = self.consumer_key.upper()
        default_realm = "test_realm" if consumer == "TESTCONS" else "limited_poa"
        self.realm = (config.get("realm") or default_realm).strip() or default_realm
        self.base_url = (config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self._session: Optional[IbkrWebSession] = None

    def validate_config(self) -> Optional[str]:
        missing = [
            name
            for name, val in (
                ("consumer_key", self.consumer_key),
                ("access_token", self.access_token),
                ("access_token_secret", self.access_token_secret),
                ("signature_key_pem", self._signature_pem),
                ("encryption_key_pem", self._encryption_pem),
                ("dh_prime", self._dh_prime_raw),
            )
            if not val
        ]
        if missing:
            return f"IBKR Web API 凭证不完整: {', '.join(missing)}"
        try:
            self.signature_key = _load_rsa_private_key(self._signature_pem)
            self.encryption_key = _load_rsa_private_key(self._encryption_pem)
            self.dh_prime = _parse_dh_prime(self._dh_prime_raw)
        except Exception as exc:  # noqa: BLE001
            return f"IBKR Web API 密钥解析失败: {exc}"
        return None

    def ensure_lst(self, http_request) -> IbkrWebSession:
        """http_request(method, url, headers) -> response-like with .ok/.status_code/.json()/.cookies"""
        if self._session and self._session.is_fresh():
            return self._session
        self._session = self._fetch_lst(http_request)
        return self._session

    def set_api_cookie(self, cookie: Optional[str]) -> None:
        if self._session is not None:
            self._session.api_cookie = cookie

    def auth_headers(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        lst: Optional[IbkrWebSession] = None,
    ) -> Dict[str, str]:
        session = lst or self._session
        if session is None:
            raise RuntimeError("尚未获取 Live Session Token")
        url = f"{self.base_url}{path}"
        oauth_params: Dict[str, str] = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
        }
        sign_params = dict(oauth_params)
        if query:
            for k, v in query.items():
                if v is None:
                    continue
                sign_params[str(k)] = str(v)
        params_string = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
        base_string = f"{method.upper()}&{_rfc3986(url)}&{_rfc3986(params_string)}"
        digest = hmac.new(
            key=base64.b64decode(session.live_session_token),
            msg=base_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        oauth_params["oauth_signature"] = quote_plus(base64.b64encode(digest).decode("utf-8"))
        oauth_params["realm"] = self.realm
        auth = "OAuth " + ", ".join(f'{k}="{v}"' for k, v in sorted(oauth_params.items()))
        headers = {
            "Authorization": auth,
            "User-Agent": "sigtrades/ibkr-web",
            "Accept": "*/*",
        }
        if session.api_cookie:
            headers["Cookie"] = f"api={session.api_cookie}"
        return headers

    def _decrypt_access_token_secret(self) -> bytes:
        if self.encryption_key is None:
            raise RuntimeError("encryption_key 未就绪")
        cipher = base64.b64decode(self.access_token_secret)
        return self.encryption_key.decrypt(cipher, padding.PKCS1v15())

    def _fetch_lst(self, http_request) -> IbkrWebSession:
        if self.signature_key is None or self.dh_prime is None:
            raise RuntimeError("OAuth 密钥未就绪，请先 validate_config")
        dh_random = secrets.randbits(256)
        dh_challenge = hex(pow(self.dh_generator, dh_random, self.dh_prime))[2:]
        prepend_bytes = self._decrypt_access_token_secret()
        prepend = prepend_bytes.hex()

        url = f"{self.base_url}/oauth/live_session_token"
        oauth_params: Dict[str, str] = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
            "oauth_signature_method": "RSA-SHA256",
            "diffie_hellman_challenge": dh_challenge,
        }
        params_string = "&".join(f"{k}={v}" for k, v in sorted(oauth_params.items()))
        base_string = f"{prepend}POST&{quote_plus(url)}&{_rfc3986(params_string)}"
        signature = self.signature_key.sign(
            base_string.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        oauth_params["oauth_signature"] = quote_plus(base64.b64encode(signature).decode("utf-8"))
        oauth_params["realm"] = self.realm
        headers = {
            "Authorization": "OAuth " + ", ".join(
                f'{k}="{v}"' for k, v in sorted(oauth_params.items())
            ),
            "User-Agent": "sigtrades/ibkr-web",
        }
        resp = http_request("POST", url, headers)
        if getattr(resp, "status_code", 0) != 200:
            body = getattr(resp, "text", "") or ""
            raise RuntimeError(f"获取 Live Session Token 失败 HTTP {resp.status_code}: {body[:400]}")
        data = resp.json()
        dh_response = str(data.get("diffie_hellman_response") or "")
        lst_signature = str(data.get("live_session_token_signature") or "")
        expires = int(data.get("live_session_token_expiration") or 0)
        if not dh_response or not lst_signature:
            raise RuntimeError("Live Session Token 响应缺少必要字段")

        B = int(dh_response, 16)
        K = pow(B, dh_random, self.dh_prime)
        hex_bytes_k = _k_to_bytes(K)
        computed_lst = base64.b64encode(
            hmac.new(hex_bytes_k, prepend_bytes, hashlib.sha1).digest()
        ).decode("utf-8")
        check = hmac.new(
            key=base64.b64decode(computed_lst),
            msg=self.consumer_key.encode("utf-8"),
            digestmod=hashlib.sha1,
        ).hexdigest()
        if check != lst_signature:
            raise RuntimeError("Live Session Token 校验失败（签名不匹配）")
        logger.info("IBKR Web API LST 就绪，expires_ms=%s", expires)
        return IbkrWebSession(live_session_token=computed_lst, expires_at_ms=expires)

    @staticmethod
    def build_query_url(path: str, query: Optional[Dict[str, Any]]) -> str:
        if not query:
            return path
        return f"{path}?{urlencode({k: v for k, v in query.items() if v is not None})}"
