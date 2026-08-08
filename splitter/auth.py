from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from .config import (
    AUTH_ALGORITHMS,
    AUTH_AUDIENCE,
    AUTH_AUTHORIZED_PARTIES,
    AUTH_ISSUER,
    AUTH_JWKS_URL,
    AUTH_MODE,
)


class AuthError(RuntimeError):
    def __init__(self, code: str, status_code: int = 401) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class Principal:
    subject: str
    claims: dict[str, object]


_JWK_CLIENT = None
_JWK_LOCK = Lock()


def authenticate(authorization: str | None) -> Principal:
    if AUTH_MODE == "disabled":
        return Principal(subject="local-development", claims={"auth_mode": "disabled"})
    if AUTH_MODE != "jwt":
        raise AuthError("unsupported_auth_mode", 503)
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("authentication_required")
    if not AUTH_JWKS_URL or not AUTH_ISSUER:
        raise AuthError("authentication_not_configured", 503)

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AuthError("authentication_required")
    try:
        import jwt

        signing_key = _jwk_client(jwt).get_signing_key_from_jwt(token)
        decode_options = {
            "require": ["exp", "iat", "sub"],
            "verify_aud": bool(AUTH_AUDIENCE),
        }
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(AUTH_ALGORITHMS),
            audience=AUTH_AUDIENCE,
            issuer=AUTH_ISSUER,
            options=decode_options,
        )
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("invalid_access_token") from exc
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthError("invalid_access_token")
    if AUTH_AUTHORIZED_PARTIES:
        authorized_party = str(claims.get("azp") or "").strip()
        if authorized_party not in AUTH_AUTHORIZED_PARTIES:
            raise AuthError("invalid_access_token")
    return Principal(subject=subject, claims=dict(claims))


def _jwk_client(jwt_module):
    global _JWK_CLIENT
    with _JWK_LOCK:
        if _JWK_CLIENT is None:
            _JWK_CLIENT = jwt_module.PyJWKClient(AUTH_JWKS_URL, cache_keys=True)
        return _JWK_CLIENT
