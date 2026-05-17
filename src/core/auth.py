"""认证与令牌工具。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


_PBKDF2_ITERATIONS = 210000


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _json_dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """使用 PBKDF2-HMAC-SHA256 哈希密码。"""
    if salt is None:
        salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        _b64url_encode(salt),
        _b64url_encode(derived),
    )


def verify_password(password: str, stored: str) -> bool:
    """校验密码哈希。"""
    try:
        scheme, iteration_text, salt_text, hash_text = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        salt = _b64url_decode(salt_text)
        expected = _b64url_decode(hash_text)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def token_hash(token: str) -> str:
    """用于数据库检索的 token 摘要。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    secret_key: str,
    subject: str,
    phone: str,
    display_name: Optional[str],
    status: str = "active",
    expires_delta_minutes: int,
) -> str:
    """创建带 HMAC 签名的简易访问令牌。"""
    issued_at = _utc_now()
    expires_at = issued_at + timedelta(minutes=expires_delta_minutes)
    payload = {
        "sub": subject,
        "phone": phone,
        "display_name": display_name,
        "status": status,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": "access",
        "jti": secrets.token_hex(16),
    }
    payload_text = _json_dumps(payload)
    payload_b64 = _b64url_encode(payload_text.encode("utf-8"))
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}"


def decode_access_token(token: str, secret_key: str) -> Dict[str, Any]:
    """验证并解析访问令牌。"""
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("无效的访问令牌") from exc

    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    provided_signature = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("访问令牌签名无效")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    if payload.get("typ") != "access":
        raise ValueError("访问令牌类型不正确")

    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    if expires_at < _utc_now():
        raise ValueError("访问令牌已过期")
    return payload


def bearer_token_from_header(authorization: Optional[str]) -> Optional[str]:
    """从 Authorization 头中提取 Bearer token。"""
    if not authorization:
        return None
    prefix = "bearer "
    value = authorization.strip()
    if not value.lower().startswith(prefix):
        return None
    token = value[len(prefix):].strip()
    return token or None


def access_token_from_authorization(
    authorization: Optional[str],
    *,
    allow_raw_token: bool = False,
) -> Optional[str]:
    """从 Authorization 头或 WebSocket query 参数中提取访问令牌。"""
    token = bearer_token_from_header(authorization)
    if token:
        return token
    if allow_raw_token and authorization:
        raw = authorization.strip()
        return raw or None
    return None
