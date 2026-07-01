from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os

from app.core.config import settings

JWT_ALGORITHM = "HS256"
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"


class AuthError(Exception):
    """认证相关业务异常。"""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password: str, iterations: int | None = None) -> str:
    """生成 PBKDF2-SHA256 密码哈希，兼容旧项目里的认证习惯。"""
    rounds = iterations or settings.auth_pbkdf2_iterations
    salt = _b64url_encode(os.urandom(16))
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return f"{PASSWORD_HASH_PREFIX}${rounds}${salt}${_b64url_encode(dk)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """校验明文密码和数据库中的 PBKDF2 哈希是否一致。"""
    try:
        prefix, iterations_text, salt, hash_value = stored_hash.split("$", 3)
        if prefix != PASSWORD_HASH_PREFIX:
            return False
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False

    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return hmac.compare_digest(_b64url_encode(dk), hash_value)


def _sign(signing_input: bytes) -> str:
    signature = hmac.new(settings.auth_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(signature)


def create_access_token(user_id: str, username: str, tenant_id: str) -> str:
    """创建 JWT，payload 内只放最小身份信息，权限仍从数据库加载。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "tenant_id": tenant_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.auth_token_expire_minutes)).timestamp()),
    }
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    return f"{header_b64}.{payload_b64}.{_sign(signing_input)}"


def decode_access_token(token: str) -> dict:
    """解析并校验 JWT。"""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise AuthError("无效的登录凭证") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    if not hmac.compare_digest(signature_b64, _sign(signing_input)):
        raise AuthError("无效的登录凭证")

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise AuthError("无效的登录凭证") from exc

    if header.get("alg") != JWT_ALGORITHM or payload.get("type") != "access":
        raise AuthError("无效的登录凭证")

    if int(datetime.now(timezone.utc).timestamp()) >= int(payload.get("exp", 0)):
        raise AuthError("登录已过期，请重新登录")

    return payload
