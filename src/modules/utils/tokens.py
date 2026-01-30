import os
import json
import hmac
import time
# import uuid
import base64
import asyncio
import inspect
# import logging
from functools import wraps
from typing import Any, Callable, TypeVar
from modules.utils.log_utils import get_logger # , log_tree

# from pathlib import Path
# from contextlib import contextmanager
# from fastmcp import FastMCP
# mcp = FastMCP(name="MCP-HMAC-LongJobs")



# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)



# =============================================================================
# 1) HMAC session tokens
# =============================================================================

# Keep this secret safe (env/secret manager). Rotatable with KEY_ID if you prefer.
SECRET = os.environ.get("MCP_HMAC_SECRET", "dev-only-change-me")  # <- change in prod!
TOKEN_TTL_SECONDS = 3600  # 1 hour default

def default_ttl() -> int:
    return TOKEN_TTL_SECONDS

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _sign(msg: bytes) -> str:
    return _b64url(hmac.new(SECRET.encode("utf-8"), msg, digestmod="sha256").digest())


def issue_token(session_id: str, ttl_s: int = TOKEN_TTL_SECONDS) -> str:
    expires = time.time() + ttl_s
    payload = {"sid": session_id, "exp": expires}
    msg = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = _sign(msg)
    return _b64url(msg) + "." + sig

def retrieve_sid(token: str)->str:
    payload = verify_token(token)
    return payload.get('sid',0)

def verify_token(token: str) -> dict:
    try:
        body_b64, sig = token.split(".", 1)
    except ValueError as e:
        raise ValueError("invalid token format") from e
    msg = _b64url_decode(body_b64)
    expected = _sign(msg)
    if not hmac.compare_digest(sig, expected):
        raise ValueError("invalid token signature")
    payload = json.loads(msg.decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("token expired")
    if "sid" not in payload:
        raise ValueError("token missing sid")
    return payload


T = TypeVar("T")


def requires_token(fn: Callable[..., T]) -> Callable[..., Any]:
    """Decorator: require a 'token' arg, verify it, and inject session_id keyword-only if needed."""
    sig = inspect.signature(fn)

    wants_session_id = "session_id" in sig.parameters

    if asyncio.iscoroutinefunction(fn):
        async def wrapper(*args, **kwargs):
            token = kwargs.get("token", "")
            if not token:
                return {"error": "missing token"}
            payload = verify_token(token)  # may raise ValueError
            if wants_session_id:
                kwargs["session_id"] = payload["sid"]
            return await fn(*args, **kwargs)
    else:
        def wrapper(*args, **kwargs):
            token = kwargs.get("token", "")
            if not token:
                return {"error": "missing token"}
            payload = verify_token(token)
            if wants_session_id:
                kwargs["session_id"] = payload["sid"]
            return fn(*args, **kwargs)

    return wraps(fn)(wrapper)


