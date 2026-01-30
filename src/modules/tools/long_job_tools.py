# import logging
import uuid
import time
# import asyncio
from typing import TypeVar, Optional, Dict
# from pathlib import Path
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from modules.utils.jobs import JobState, _JOBS, jk, sweep_jobs 
from modules.utils.tokens import issue_token, requires_token, retrieve_sid, default_ttl
from modules.utils.log_utils import get_logger # , log_tree

T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)




# =============================================================================
# 3) Job control API
# =============================================================================

def get_session_token(client_hint: str | None = None,
                      ttl_s: Optional[int] = None) -> Dict:
    """Return a new HMAC session token.

    Args:
        client_hint: Optional string to log/debug; not used in token.
        ttl_s: Optional TTL override in seconds.

    Returns:
        {"session_id": ..., "token": ..., "expires_in": ...}
    """
    logger.info("✅ Issuing new session token (client_hint=%s, ttl_s=%s).",client_hint, ttl_s)
    sid = str(uuid.uuid4())
    ttl = ttl_s if ttl_s is not None else default_ttl()
    exp = time.time() + ttl
    logger.info("✅ Token sid: %s, exp: %i.", sid, exp)
    token = issue_token(sid, ttl_s=ttl)
    return {"session_id": sid, "token": token, "exp": int(exp), "expires_in": int(ttl)}



# @requires_token
# async def start_long_job(payload: str,token: str, timeout_s: float | None = 300.0,
#                          *, session_id: str) -> dict:
#     """Start a demo long job (simulated work), returning a job_id."""
#     job_id = str(uuid.uuid4())
#     job = Job(job_id=job_id, session_id=session_id, timeout_s=timeout_s)
#     _JOBS[jk(session_id, job_id)] = job
#     # Next line starts the 'test' job. Uncomment to enable simulated work.
#     # job.task = asyncio.create_task(run_with_timeout(job, _simulate_work(job, payload)))
#     return {"job_id": job_id, "state": job.state, "progress": job.progress}


@requires_token
def get_job_status(job_id: str, token: str) -> Dict:
    """Get status/progress of a job for this session_id."""
    session_id = retrieve_sid(token)
    job = _JOBS.get(jk(session_id, job_id))
    if not job:
        raise ToolError("No such job for this session")

    # if job.state == JobState.FAILED:
    #     err = job.error if job.error is not None else 'unknown error'
    #     raise ToolError(
    #         f"Job {job.job_id} failed: {err}"
    #     )

    return {
        "job_id": job.job_id,
        "state": job.state,
        "progress": job.progress,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": job.error,
        }


@requires_token
def get_job_result(job_id: str, token: str) -> Dict:
    """Get the result for a job in this session.

    Behavior:
      - If DONE: return the stored result and REMOVE the job from _JOBS.
      - If terminal error (FAILED / TIMED_OUT / CANCELED): return error info and REMOVE the job.
      - If still running/pending: return "job not complete" without removing the job.
    """
    # Safety net cleanup (doesn't affect correctness).
    sweep_jobs(max_age_s=60 * 60, keep_running=True)

    session_id = retrieve_sid(token)
    key = jk(session_id, job_id)
    job = _JOBS.get(key)
    if not job:
        raise ToolError("No such job for this session")

    if job.state in (JobState.DONE, JobState.FAILED, JobState.TIMED_OUT, JobState.CANCELED):
        _JOBS.pop(key, None)
        return {
            "job_id": job.job_id,
            "state": job.state.value,
            "result": job.result if job.state == JobState.DONE else None,
            "error": job.error,
            "error_type": getattr(job, "error_type", None),
        }

    # Job is running/pending
    return {"job_id": job.job_id, "state": job.state.value, "error": "job not complete"}


@requires_token
async def cancel_job(job_id: str, token: str) -> Dict:
    """ Cancel a running job for this session_id.
            Args:
                job_id (str): The ID of the job to cancel.
                token (str): The HMAC session token.
                session_id (str): Injected session ID from token.
            Returns:
                dict: A dictionary indicating success or failure of cancellation.
"""
    session_id = retrieve_sid(token)
    job = _JOBS.get(jk(session_id, job_id))
    if not job:
        raise ToolError("No such job for this session")

    if job.task and not job.task.done():
        job.task.cancel()
        return {"job_id": job_id, "state": "cancel_requested"}
    return {"job_id": job_id, "state": job.state}


def register(mcp: T) -> None:
    """Register long job tools with MCPServer."""
    logger.info("✅ Registering long job tools that don't need tokens")
    mcp.tool(tags=["public", "api"])(get_session_token)
    # mcp.tool(tags=["public", "api"])(start_long_job)
    mcp.tool(tags=["public", "api"])(get_job_status)
    mcp.tool(tags=["public", "api"])(get_job_result)
    mcp.tool(tags=["public", "api"])(cancel_job)


# def register_long(mcp: T) -> None:
#     """
#     Register long job tools with the MCP instance as a long job.

#     This registers ASYNC variants so the job can be cancelled while transcribing.
#     The sync versions remain available for CLI/testing.
#     """
#     logger.debug("✅ Registering YouTube transcript tools (async/cancellable)")



