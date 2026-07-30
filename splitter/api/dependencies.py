from __future__ import annotations

from typing import Annotated

from fastapi import Header

from splitter.auth import Principal, authenticate

from .responses import APIError


def current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    return authenticate(authorization)


def idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > 200:
        raise APIError(400, "idempotency_key_too_long")
    return normalized
