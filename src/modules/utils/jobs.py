import time
import uuid
import asyncio
import inspect
import logging
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from dataclasses import dataclass, field
from enum import Enum
from ..utils.tokens import verify_token
from mcp.types import CallToolResult, TextContent  # if you have the official mcp package
# OR, if you intend to use your generated bindings file, import from wherever types.py lives:
# from ..utils.types import CallToolResult, TextContent

from fastmcp import FastMCP
from modules.utils.log_utils import get_logger

# import base64
# import argparse
# from pathlib import Path

# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)


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
    status: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    timeout_s: Optional[float] = 300.0
    task: Optional[asyncio.Task] = None


# Jobs are namespaced by session_id
# key: (session_id, job_id)
_JOBS: Dict[tuple[str, str], Job] = {}


def jk(sid: str, jid: str) -> tuple[str, str]:
    return (sid, jid)

def sweep_jobs(*, max_age_s: float = 60 * 60, keep_running: bool = False) -> int:
    """Best-effort cleanup of old jobs from the in-memory store.

    This is a safety net in case clients never fetch results (crash, network issues, etc.).
    Args:
        max_age_s: Remove jobs older than this many seconds (based on finished_at when available,
                   otherwise created_at).
        keep_running: If True, only sweep terminal jobs. If False, may also sweep long-stuck running jobs.

    Returns:
        Number of jobs removed.
    """
    now = time.time()
    removed = 0
    for key, job in list(_JOBS.items()):
        ts = job.finished_at if job.finished_at is not None else job.created_at
        age = now - ts
        if age <= max_age_s:
            continue
        if keep_running and job.state in (JobState.PENDING, JobState.RUNNING):
            continue
        _JOBS.pop(key, None)
        removed += 1
    return removed



async def _run_with_timeout(job: Job, coro: asyncio.coroutines):
    """Run a job coroutine with an optional timeout, capturing terminal state.

    This function is responsible for translating execution outcomes into JobState
    and recording error metadata. It should NOT raise exceptions to callers,
    except that CancelledError is re-raised so asyncio cancellation semantics remain intact.
    """
    try:
        if job.timeout_s is not None:
            await asyncio.wait_for(coro, timeout=job.timeout_s)
        else:
            await coro

    except asyncio.TimeoutError:
        job.state = JobState.TIMED_OUT
        job.error = "timed out"
        job.error_type = "TimeoutError"

    except asyncio.CancelledError:
        job.state = JobState.CANCELED
        job.error = "canceled"
        job.error_type = "CancelledError"
        raise

    except Exception as e:
        job.state = JobState.FAILED
        job.error = str(e)
        job.error_type = type(e).__name__
        try:
            import traceback as _tb
            job.traceback = _tb.format_exc()
        except Exception:
            # best-effort only
            job.traceback = None

    finally:
        # Ensure we always stamp finished_at for terminal states.
        if job.finished_at is None and job.state in (
            JobState.DONE,
            JobState.FAILED,
            JobState.TIMED_OUT,
            JobState.CANCELED,
        ):
            job.finished_at = time.time()


# -----------------------------------------
# Long-tool registration wrapper (token + job launch)
# -----------------------------------------

def _make_longjob_launch_wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a wrapper that *launches* the underlying tool as a background Job.

    Registration time:
      - We register this wrapper as the MCP tool callable.
      - We override __signature__ so FastMCP exposes an added keyword-only `token`
        and 'timeout_s. parameters

    Call time (when an MCP client invokes the tool):
      1) Verify token -> derive session_id
      2) Create Job(session_id, job_id) and store in _JOBS
      3) Schedule the underlying tool call in background
      4) Return {job_id, state, progress} immediately

    Notes:
      - Underlying tools are NOT required to accept `token`.
      - If the underlying tool accepts `session_id`, it will be injected.
      - Sync tools run via asyncio.to_thread; async tools are awaited.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())

    # Underlying tools must not use *args for FastMCP compatibility.
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
        raise ValueError(f"Tool {fn.__name__} uses *args and cannot be registered as a tool")

    has_token = "token" in sig.parameters
    has_timeout = "timeout_s" in sig.parameters
    has_progress_cb = "progress_cb" in sig.parameters


    # Add keyword-only token if tool doesn't already have it
    if not has_token:
        params.append(
            inspect.Parameter(
                "token",
                kind=inspect.Parameter.KEYWORD_ONLY,
                # default="",
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
                annotation=Optional[int],
            )
        )

    if not has_progress_cb:
        params.append(
            inspect.Parameter(
                "progress_cb",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=Any,   # IMPORTANT: schema-friendly
            )
        )

    new_sig = sig.replace(parameters=params)



    async def wrapper(**kwargs):
        # Using call_kwargs to avoid mutating kwargs directly
        call_kwargs = dict(kwargs)

        token = call_kwargs.pop("token", "")
        if not token:
            return {"error": "missing token"}

        payload = verify_token(token)  # may raise ValueError

        session_id = payload["sid"]

        timeout_s = call_kwargs.pop("timeout_s", None)

        progress_cb = call_kwargs.pop("progress_cb", None)

        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, session_id=session_id, timeout_s=timeout_s)
        _JOBS[jk(session_id, job_id)] = job

        async def _work():
            job.state = JobState.RUNNING
            job.started_at = time.time()
            job.progress = 0.01

            if "progress_cb" in sig.parameters and "progress_cb" not in call_kwargs:
                loop = asyncio.get_running_loop()

                def _progress_cb(fraction: float, message: str = "") -> None:
                    # clamp and update job.progress safely
                    f = float(fraction)
                    if f < 0.0:
                        f = 0.0
                    elif f > 1.0:
                        f = 1.0

                    # In case callback is invoked from a worker thread
                    loop.call_soon_threadsafe(setattr, job, "progress", f)

                    # Optional: if you add `job.status: str = ""` to Job dataclass:
                    loop.call_soon_threadsafe(setattr, job, "status", message)

                call_kwargs["progress_cb"] = _progress_cb

            if asyncio.iscoroutinefunction(fn):
                result = await fn(**call_kwargs)
            else:
                result = await asyncio.to_thread(fn, **call_kwargs)

            job.result = result
            job.progress = 1.0
            job.state = JobState.DONE
            job.finished_at = time.time()

        job.task = asyncio.create_task(_run_with_timeout(job, _work()))

        job_info = {"job_id": job_id, "state": job.state.value,
                    "progress": float(job.progress), "status": job.status}

        return job_info

    wraps(fn)(wrapper)

    # Ensure type hints include any added parameters so schema generation works.
    wrapper.__annotations__ = dict(getattr(fn, "__annotations__", {}) or {})

    if "token" in new_sig.parameters:
        wrapper.__annotations__.setdefault("token", str)

    if "timeout_s" in new_sig.parameters:
        wrapper.__annotations__.setdefault("timeout_s", int | None)
    
    # progress_cb MUST override (never setdefault)   
    # If a progress_cb is passed it can overwrite the Any type
    # possibly causing mcp schema checks to fail.
    if "progress_cb" in new_sig.parameters:
        wrapper.__annotations__["progress_cb"] = Any

    # Critical: launch wrapper returns job-info dict
    wrapper.__annotations__["return"] = Dict[str, Any]
    wrapper.__signature__ = new_sig  # tell FastMCP the effective signature
    return wrapper


@contextmanager
def long_tools_require_token(mcp: FastMCP):
    """ While active, any tool registered via mcp.tool(...) will be wrapped so it
        launches the underlying tool as a background Job and requires a keyword-only 
        `token` argument when invoked.
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


