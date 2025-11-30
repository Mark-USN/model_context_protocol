""" MCP module: HMAC-authenticated long-running jobs with session isolation."""
import os
# import sys
import hmac
import json
import time
import uuid
import base64
import asyncio
import logging
import argparse
# import importlib
# import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict,Optional, TypeVar, cast
from dataclasses import dataclass, field
from enum import Enum
from fastmcp import FastMCP
from ..utils.prompt_md_loader import register_prompts_from_markdown
from ..utils.prompt_loader import register_prompts
from ..utils.tool_loader import register_tools


# mcp = FastMCP(name="MCP-HMAC-LongJobs")


# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)


# -----------------------------
# Paths to tool, prompt, resource packages
# -----------------------------
_MODULES_DIR = Path(__file__).parents[1].resolve()
_TOOLS_DIR = _MODULES_DIR / "tools"
_PROMPTS_DIR = _MODULES_DIR / "prompts"
_RESOURCES_DIR = _MODULES_DIR / "resources"


# -----------------------------
# From demo_server.py: Paths to tool, prompt, resource packages
# -----------------------------

mcp = FastMCP(
    name="DemoServer",
    include_tags={"public", "api"},
    exclude_tags={"internal", "deprecated"},
    on_duplicate_tools="error",
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    # strict_input_validation=False,
    include_fastmcp_meta=False,
)

# -----------------------------------------
# Attach everything to FastMCP at startup
# -----------------------------------------
def attach_everything():
    """ 20251101 MMH attach_everything registers all tools and prompts to the FastMCP server.
        Warning: The server will pull in all the code from a tool or prompt package.
        Any error in a file will cause the tools or prompts in that package to be ignored.
        Make sure you trust the code in those packages!
    """
    register_tools(mcp, package=_TOOLS_DIR)
    logger.info("✅	 Tools registered.")

    register_prompts_from_markdown(mcp, prompts_dir=_PROMPTS_DIR)
    logger.info("✅	 Markdown files parsed and prompts registered.")

    register_prompts(mcp, package=_PROMPTS_DIR)
    logger.info("✅	 Prompt functions registered.")

def launch_server(host:str="127.0.0.1", port:int=8085):
    """ 20251101 MMH launch_server
        The entry point to start the FastMCP server. 
        Launch the FastMCP server with all tools and prompts attached. 
    """
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅	 Server started on http://{host}:{port}")



# =============================================================================
# 1) HMAC session tokens
# =============================================================================

# Keep this secret safe (env/secret manager). Rotatable with KEY_ID if you prefer.
SECRET = os.environ.get("MCP_HMAC_SECRET", "dev-only-change-me")  # <- change in prod!
TOKEN_TTL_SECONDS = 3600  # 1 hour default

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def _unb64url(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def _sign(payload: dict) -> str:
    """
    Compact JWS-like: base64url(header).base64url(payload).base64url(sig)
    header is static: {"alg":"HS256","typ":"JWT"}
    """
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p_b64 = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    msg = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(SECRET.encode(), msg, "sha256").digest()
    return f"{h_b64}.{p_b64}.{_b64url(sig)}"

def _verify(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("bad token format")
        h_b64, p_b64, s_b64 = parts
        msg = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(SECRET.encode(), msg, "sha256").digest()
        given = _unb64url(s_b64)
        if not hmac.compare_digest(expected, given):
            raise ValueError("signature mismatch")
        payload = json.loads(_unb64url(p_b64))
    except Exception as e:
        raise ValueError(f"invalid token: {e}") from e

    now = int(time.time())
    if "exp" in payload and now > int(payload["exp"]):
        raise ValueError("token expired")
    if "nbf" in payload and now < int(payload["nbf"]):
        raise ValueError("token not yet valid")
    return payload

# Issue a session token (short-lived, opaque, HMAC-signed)
@mcp.tool
def get_session_token(client_hint: str | None = None,
                      ttl_seconds: int = TOKEN_TTL_SECONDS) -> dict:
    """
    Returns a short-lived signed token with a unique session_id.
    Clients should present this 'token' to protected tools.
    """
    now = int(time.time())
    session_id = str(uuid.uuid4())
    payload = {
        "sid": session_id,
        "iat": now,
        "nbf": now,
        "exp": now + int(ttl_seconds),
        "scope": ["long_jobs","protected_tools"],
        "client_hint": client_hint,
    }
    return {"token": _sign(payload), "sid": session_id, "expires_in": ttl_seconds}

# -----------------------------------------------------------------------------
# Decorator to require and verify token. Extracts the session_id for namespacing
# -----------------------------------------------------------------------------
F = TypeVar("F", bound=Callable[..., Any])

def requires_token(fn: F) -> F:
    """
    Wrap a tool function that has a parameter named 'token'.
    Verifies token and injects 'session_id' kwarg for convenience.
    """
    async def _async_wrapper(*args, **kwargs):
        token = kwargs.get("token")
        if not token:
            return {"error": "missing token"}
        try:
            payload = _verify(token)
        except ValueError as e:
            return {"error": f"auth failed: {e}"}
        kwargs["session_id"] = payload["sid"]
        return await fn(*args, **kwargs)

    def _sync_wrapper(*args, **kwargs):
        token = kwargs.get("token")
        if not token:
            return {"error": "missing token"}
        try:
            payload = _verify(token)
        except ValueError as e:
            return {"error": f"auth failed: {e}"}
        kwargs["session_id"] = payload["sid"]
        return fn(*args, **kwargs)

    # preserve sync/async behavior
    if asyncio.iscoroutinefunction(fn):
        return cast(F, _async_wrapper)

    return cast(F, _sync_wrapper)

# =============================================================================
# 2) Long-job infrastructure (per-session isolation)
# =============================================================================

class JobState(str, Enum):
    """ Possible states for a long-running job. """
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"

@dataclass
class Job:
    """ Represents a long-running job. """
    job_id: str
    session_id: str
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    state: JobState = JobState.PENDING
    progress: float = 0.0
    result: Optional[Any] = None
    error: Optional[str] = None
    timeout_s: Optional[float] = 300.0
    task: Optional[asyncio.Task] = None

# Jobs are namespaced by session_id
# key: (session_id, job_id)
_JOBS: Dict[tuple[str, str], Job] = {}

def _jk(sid: str, jid: str) -> tuple[str, str]:
    return (sid, jid)

async def _simulate_work(job: Job, payload: str):
    job.state = JobState.RUNNING
    job.started_at = time.time()
    steps = 20
    for i in range(steps):
        if job.state == JobState.CANCELED:
            raise asyncio.CancelledError()
        await asyncio.sleep(0.25)
        job.progress = (i + 1) / steps
    job.result = f"Processed payload: {payload!r}"
    job.state = JobState.DONE
    job.finished_at = time.time()

async def _run_with_timeout(job: Job, coro: asyncio.coroutines):
    try:
        if job.timeout_s:
            await asyncio.wait_for(coro, timeout=job.timeout_s)
        else:
            await coro
    except asyncio.TimeoutError:
        job.state = JobState.TIMED_OUT
        job.error = f"timed out after {job.timeout_s}s"
        job.finished_at = time.time()
    except asyncio.CancelledError:
        job.state = JobState.CANCELED
        job.error = "canceled"
        job.finished_at = time.time()
        raise
    except Exception as e:  # pylint: disable=broad-exception-caught
        job.state = JobState.FAILED
        job.error = f"{type(e).__name__}: {e}"
        job.finished_at = time.time()

# -----------------------------------------------------------------------------
# Protected long-job tools (require token)
# -----------------------------------------------------------------------------

@mcp.tool
@requires_token
async def start_long_job(payload: str, token: str, timeout_s: float | None = 300.0,
                         *, session_id: str) -> dict:
    """
    Start a background job bound to this session_id. Returns job_id.
    """
    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, session_id=session_id, timeout_s=timeout_s)
    _JOBS[_jk(session_id, job_id)] = job
    job.task = asyncio.create_task(_run_with_timeout(job, _simulate_work(job, payload)))
    return {"job_id": job_id, "state": job.state, "progress": job.progress}

@mcp.tool
@requires_token
def get_job_status(job_id: str, token: str, *, session_id: str) -> dict:
    """ Get status of a job for this session_id. 
            Args: 
                job_id (str): The ID of the job to query.
                token (str): The HMAC session token.
                session_id (str): Injected session ID from token.
            Returns:
                dict: A dictionary with job status information.
    """
    job = _JOBS.get(_jk(session_id, job_id))
    if not job:
        return {"error": "no such job for this session"}
    return {
        "job_id": job.job_id,
        "state": job.state,
        "progress": job.progress,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": job.error,
        "has_result": job.result is not None,
    }

@mcp.tool
@requires_token
def get_job_result(job_id: str, token: str, *, session_id: str) -> dict:
    """ Get result of a completed job for this session_id.
            Args:
                job_id (str): The ID of the job to get the result for.
                token (str): The HMAC session token.
                session_id (str): Injected session ID from token.
            Returns:
                dict: A dictionary with the job result or an error message.
    """
    job = _JOBS.get(_jk(session_id, job_id))
    if not job:
        return {"error": "no such job for this session"}
    if job.state != JobState.DONE:
        return {"error": f"job not done (state={job.state})"}
    return {"job_id": job.job_id, "result": job.result}

@mcp.tool
@requires_token
async def cancel_job(job_id: str, token: str, *, session_id: str) -> dict:
    """ Cancel a running job for this session_id.
            Args:
                job_id (str): The ID of the job to cancel.
                token (str): The HMAC session token.
                session_id (str): Injected session ID from token.
            Returns:
                dict: A dictionary indicating success or failure of cancellation.
"""
    job = _JOBS.get(_jk(session_id, job_id))
    if not job:
        return {"error": "no such job for this session"}
    if job.state in {JobState.DONE, JobState.FAILED, JobState.CANCELED, JobState.TIMED_OUT}:
        return {"ok": False, "info": f"already finished (state={job.state})"}
    if job.task and not job.task.done():
        job.state = JobState.CANCELED
        job.task.cancel()
        try:
            await job.task
        except asyncio.CancelledError:
            pass
        return {"ok": True, "state": job.state}
    return {"ok": False, "info": "no running task found"}

# =============================================================================
# 3) Short / regular tools
# =============================================================================

# A) PUBLIC short tool (no token required)
@mcp.tool
def echo(text: str) -> str:
    """ Simple echo tool (no auth required).
            Args:
                text (str): The text to echo back.
            Returns:
                str: The echoed text.
    """
    return text

# B) PROTECTED short tool (requires token) — e.g., reads user-owned server data
@mcp.tool
@requires_token
def list_my_jobs(token: str, *, session_id: str) -> dict:
    """ List all jobs for this session_id.
            Args:
                token (str): The HMAC session token.
                session_id (str): Injected session ID from token.
            Returns:
                dict: A dictionary with count and list of jobs.
    """
    mine = [
        {
            "job_id": jid,
            "state": job.state,
            "progress": job.progress,
            "has_result": job.result is not None,
        }
        for (sid, jid), job in _JOBS.items()
        if sid == session_id
    ]
    return {"count": len(mine), "jobs": mine}

# =============================================================================

def port_type(value: str) -> int:
    """ 20251101 MMH port_type
        Custom argparse type that validates a TCP port number.
    """
    try:
        port = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Port must be an integer (got {value!r})") from e
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"Port number must be between 1 and 65535 (got {port})")
    return port



def main():
    """ 20251101 MMH main
        Main entry point when launched "stand alone" 
        Parse arguments and start the server. 
    """
    parser = argparse.ArgumentParser(description="Create and run an MCP server.")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085,
                        help="TCP port to bind/connect (default 8085).")
    args = parser.parse_args()

    launch_server(args.host, args.port)

if __name__ == "__main__":
    main()
# if __name__ == "__main__":
#     mcp.run()
