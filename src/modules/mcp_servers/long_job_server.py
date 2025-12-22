""" MCP module: HMAC-authenticated long-running jobs with session isolation."""
import os
# import sys
import hmac
import json
import time
import uuid
import base64
import asyncio
import argparse
import inspect
import logging
from contextlib import contextmanager
from functools import wraps
# import importlib
# import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from dataclasses import dataclass, field
from enum import Enum
from fastmcp import FastMCP
from ..utils.logging_config import setup_logging
from ..utils.prompt_md_loader import register_prompts_from_markdown
from ..utils.prompt_loader import register_prompts
from ..utils.tool_loader import register_tools
from ..utils.long_tool_loader import register_long_tools


# mcp = FastMCP(name="MCP-HMAC-LongJobs")

# -----------------------------
# Logging setup
# -----------------------------
setup_logging()
logger = logging.getLogger(__name__)

# -----------------------------
# Paths to tool, prompt, resource packages
# -----------------------------
_MODULES_DIR = Path(__file__).parents[1].resolve()
_TOOLS_DIR = _MODULES_DIR / "tools"
_PROMPTS_DIR = _MODULES_DIR / "prompts"
_RESOURCES_DIR = _MODULES_DIR / "resources"
_PROJECT_DIR = _MODULES_DIR.parents[1].resolve()
_CACHE_DIR = _PROJECT_DIR / "Cache" 

# -----------------------------
# From demo_server.py: Paths to tool, prompt, resource packages
# -----------------------------

mcp = FastMCP(
    name="LongJobServer",
    include_tags={"public", "api"},
    exclude_tags={"internal", "deprecated"},
    on_duplicate_tools="error",
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    # strict_input_validation=False,
    include_fastmcp_meta=False,
)


def purge_cache(days: int = 7) -> None:
    """ Purge transcript cache files older than `days` days.
        Args:
            days (int): Number of days to keep cache files. Default is 7 days.
    """
    # All audio files should be deleted after they are transcribed. So ony 
    # files that are currently being transcribed or possibly failed transcriptions
    # should be here.

    cutoff = time.time() - (days * 86400)

    audio_dir = _CACHE_DIR / "audio"
    if audio_dir.exists():
        for f in audio_dir.iterdir():
            if f.is_file() and f.stat().mt_atime < cutoff:
                f.unlink(missing_ok=True)

    transcript_dir = _CACHE_DIR / "transcripts"
    if transcript_dir.exists():
        for f in transcript_dir.iterdir():
            if f.is_file() and f.stat().mt_atime < cutoff:
                f.unlink(missing_ok=True)





# -----------------------------------------
# Long-tool registration wrapper (token + job launch)
# -----------------------------------------

def _make_longjob_launch_wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a wrapper that *launches* the underlying tool as a background Job.

    Registration time:
      - We register this wrapper as the MCP tool callable.
      - We override __signature__ so FastMCP exposes an added keyword-only `token`
        parameter (and `timeout_s`).

    Call time (when an MCP client invokes the tool):
      1) Verify token -> derive session_id
      2) Create Job(session_id, job_id) and store in _JOBS
      3) Schedule the underlying tool call in background
      4) Return {job_id, state, progress} immediately

    Notes:
      - Underlying tools are NOT required to accept `token` or `session_id`.
      - If the underlying tool accepts `session_id`, it will be injected.
      - Sync tools run via asyncio.to_thread; async tools are awaited.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())

    # Underlying tools must not use *args for FastMCP compatibility.
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
        raise ValueError(f"Tool {fn.__name__} uses *args and cannot be registered as a tool")

    wants_session_id = "session_id" in sig.parameters
    has_token = "token" in sig.parameters
    has_timeout = "timeout_s" in sig.parameters

    # Add keyword-only token if tool doesn't already have it
    if not has_token:
        params.append(
            inspect.Parameter(
                "token",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default="",
                annotation=str,
            )
        )

    # Optional per-invocation timeout override
    if not has_timeout:
        params.append(
            inspect.Parameter(
                "timeout_s",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=Optional[float],
            )
        )

    new_sig = sig.replace(parameters=params)

    async def wrapper(**kwargs):
        token = kwargs.pop("token", "")
        if not token:
            return {"error": "missing token"}

        payload = _verify(token)  # may raise ValueError
        session_id = payload["sid"]

        timeout_s = kwargs.pop("timeout_s", None)

        # Inject session_id if the underlying tool supports it
        if wants_session_id:
            kwargs.setdefault("session_id", session_id)

        # Create + store the job
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, session_id=session_id, timeout_s=timeout_s)
        _JOBS[_jk(session_id, job_id)] = job

        async def _work():
            job.state = JobState.RUNNING
            job.started_at = time.time()
            job.progress = 0.01

            if asyncio.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                result = await asyncio.to_thread(fn, **kwargs)

            job.result = result
            job.progress = 1.0
            job.state = JobState.DONE
            job.finished_at = time.time()

        job.task = asyncio.create_task(_run_with_timeout(job, _work()))
        return {"job_id": job_id, "state": job.state, "progress": job.progress}

    wraps(fn)(wrapper)

    # Ensure type hints include any added parameters so schema generation works.
    wrapper.__annotations__ = dict(getattr(fn, "__annotations__", {}) or {})
    if "token" in new_sig.parameters and "token" not in wrapper.__annotations__:
        wrapper.__annotations__["token"] = str
    if "timeout_s" in new_sig.parameters and "timeout_s" not in wrapper.__annotations__:
        wrapper.__annotations__["timeout_s"] = Optional[float]

    wrapper.__signature__ = new_sig  # tell FastMCP the effective signature
    return wrapper


@contextmanager
def long_tools_require_token(mcp: FastMCP):
    """While active, any tool registered via mcp.tool(...) will be wrapped so it
    launches the underlying tool as a background Job and requires a keyword-only `token` argument when invoked.
    """
    original_tool = mcp.tool

    def tool_with_token(*tool_args, **tool_kwargs):
        registrar = original_tool(*tool_args, **tool_kwargs)

        def decorator(fn):
            gated = _make_longjob_launch_wrapper(fn)
            return registrar(gated)

        return decorator

    mcp.tool = tool_with_token
    try:
        yield
    finally:
        mcp.tool = original_tool


# -----------------------------------------
# Attach everything to FastMCP at startup
# -----------------------------------------
def attach_everything():
    """ 20251101 MMH attach_everything registers all tools and prompts to the FastMCP server.
        Warning: The server will pull in all the code from a tool or prompt package.
        Any error in a file will cause the tools or prompts in that package to be ignored.
        Make sure you trust the code in those packages!
    """
    # Regular tools behave exactly like demo_server
    register_tools(mcp, package=_TOOLS_DIR)
    logger.info("✅\t Tools registered.")

    # Long tools: only those registered via register_long_tools are wrapped as background jobs
    with long_tools_require_token(mcp):
        register_long_tools(mcp, package=_TOOLS_DIR)
    logger.info("✅\t Long tools registered (launch as jobs; token required).")

    register_prompts_from_markdown(mcp, prompts_dir=_PROMPTS_DIR)
    logger.info("✅\t Prompts from markdown registered.")

    register_prompts(mcp, prompts_dir=_PROMPTS_DIR)
    logger.info("✅\t Prompts registered.")


def launch_server(host:str="127.0.0.1", port:int=8085):
    """ 20251101 MMH launch_server
        The entry point to start the FastMCP server. 
        Launch the FastMCP server with all tools and prompts attached. 
    """

    logger.info("✅ long_job_server started.")
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅	 Long Job Server started on http://{host}:{port}")


def main():
    parser = argparse.ArgumentParser(description="MCP long-job server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8085)
    args = parser.parse_args()

    host = args.host
    port = args.port

    logger.info("✅ long_job_server started.")
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅\t Server started on http://{host}:{port}")


# =============================================================================
# 1) HMAC session tokens
# =============================================================================

# Keep this secret safe (env/secret manager). Rotatable with KEY_ID if you prefer.
SECRET = os.environ.get("MCP_HMAC_SECRET", "dev-only-change-me")  # <- change in prod!
TOKEN_TTL_SECONDS = 3600  # 1 hour default


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _sign(msg: bytes) -> str:
    return _b64url(hmac.new(SECRET.encode("utf-8"), msg, digestmod="sha256").digest())


def _issue_token(session_id: str, ttl_s: int = TOKEN_TTL_SECONDS) -> str:
    payload = {"sid": session_id, "exp": int(time.time()) + int(ttl_s)}
    msg = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = _sign(msg)
    return _b64url(msg) + "." + sig


def _verify(token: str) -> dict:
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
            payload = _verify(token)  # may raise ValueError
            if wants_session_id:
                kwargs["session_id"] = payload["sid"]
            return await fn(*args, **kwargs)
    else:
        def wrapper(*args, **kwargs):
            token = kwargs.get("token", "")
            if not token:
                return {"error": "missing token"}
            payload = _verify(token)
            if wants_session_id:
                kwargs["session_id"] = payload["sid"]
            return fn(*args, **kwargs)

    return wraps(fn)(wrapper)


@mcp.tool
def get_session_token(client_hint: str | None = None,
                      ttl_s: int | None = None) -> dict:
    """Return a new HMAC session token.

    Args:
        client_hint: Optional string to log/debug; not used in token.
        ttl_s: Optional TTL override in seconds.

    Returns:
        {"session_id": ..., "token": ..., "expires_in": ...}
    """
    sid = str(uuid.uuid4())
    ttl = int(ttl_s) if ttl_s is not None else TOKEN_TTL_SECONDS
    token = _issue_token(sid, ttl_s=ttl)
    return {"session_id": sid, "token": token, "expires_in": ttl}


# =============================================================================
# 2) Job state + store
# =============================================================================

class JobState(str, Enum):
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
        await asyncio.sleep(0.25)
        job.progress = (i + 1) / steps
    job.result = {"echo": payload, "ts": time.time()}
    job.state = JobState.DONE
    job.finished_at = time.time()


async def _run_with_timeout(job: Job, coro: asyncio.coroutines):
    try:
        if job.timeout_s is not None:
            await asyncio.wait_for(coro, timeout=job.timeout_s)
        else:
            await coro
    except asyncio.TimeoutError:
        job.state = JobState.TIMED_OUT
        job.error = "timed out"
        job.finished_at = time.time()
    except asyncio.CancelledError:
        job.state = JobState.CANCELED
        job.error = "canceled"
        job.finished_at = time.time()
        raise
    except Exception as e:
        job.state = JobState.FAILED
        job.error = str(e)
        job.finished_at = time.time()


# =============================================================================
# 3) Job control API
# =============================================================================

@mcp.tool
@requires_token
async def start_long_job(payload: str, token: str, timeout_s: float | None = 300.0,
                         *, session_id: str) -> dict:
    """Start a demo long job (simulated work), returning a job_id."""
    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, session_id=session_id, timeout_s=timeout_s)
    _JOBS[_jk(session_id, job_id)] = job
    job.task = asyncio.create_task(_run_with_timeout(job, _simulate_work(job, payload)))
    return {"job_id": job_id, "state": job.state, "progress": job.progress}


@mcp.tool
@requires_token
def get_job_status(job_id: str, token: str, *, session_id: str) -> dict:
    """Get status/progress of a job for this session_id."""
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
    }


@mcp.tool
@requires_token
def get_job_result(job_id: str, token: str, *, session_id: str) -> dict:
    """Get the result for a job in this session.

    Behavior:
      - If DONE: return the stored result and REMOVE the job from _JOBS.
      - If terminal error (FAILED / TIMED_OUT / CANCELED): return error info and REMOVE the job.
      - If still running/pending: return "job not complete" without removing the job.
    """
    key = _jk(session_id, job_id)
    job = _JOBS.get(key)
    if not job:
        return {"error": "no such job for this session"}

    if job.state == JobState.DONE:
        # One-shot delivery: remove job after delivering result
        _JOBS.pop(key, None)
        return {"job_id": job_id, "result": job.result}

    if job.state in (JobState.FAILED, JobState.TIMED_OUT, JobState.CANCELED):
        _JOBS.pop(key, None)
        return {"job_id": job_id, "error": job.error, "state": job.state}

    return {"job_id": job_id, "error": "job not complete", "state": job.state}


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
    if job.task and not job.task.done():
        job.task.cancel()
        return {"job_id": job_id, "state": "cancel_requested"}
    return {"job_id": job_id, "state": job.state}


if __name__ == "__main__":
    main()
