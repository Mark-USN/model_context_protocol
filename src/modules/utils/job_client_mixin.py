import asyncio
import logging
import random
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class JobClientMixin:
    """Client-side helpers for FastMCP long-running job tools.

    Assumes the concrete client provides:
      - async call_tool(tool_name: str, args: dict) -> CallToolResult-like object with `.data`
    """

    _next_allowed_ts: float = 0.0  # simple per-process limiter

    async def call_long_tool_and_get_result(
        self, tool_name: str, args: dict, *, poll_s: float = 2.0
    ):
        """Launch a long-running tool and wait for its terminal result.

        Important invariants:
          - Polling (get_job_status) never clears jobs.
          - Once terminal, we ALWAYS call get_job_result to 'ack+pop' the job,
            even if the job FAILED/TIMED_OUT/CANCELED.
        """
        logger.info("Launching long-running tool: %s with args: %s", tool_name, args)

        launch = await self.call_tool(tool_name, args)
        launch_payload = getattr(launch, "data", None) or {}

        if "job_id" not in launch_payload:
            # If you accidentally hit a non-long tool, it might already be the real result.
            return launch

        job_id = launch_payload["job_id"]
        token = args["token"]

        # Poll until terminal
        while True:
            status = await self.call_tool("get_job_status", {"job_id": job_id, "token": token})
            s = getattr(status, "data", None) or {}
            state = s.get("state")
            job = s.get("job_id")
            progress = s.get("progress")
            logger.info(f"Job: {job} State: {state} Progress: {progress}.")
            if state in ("done", "failed", "timed_out", "canceled"):
                break

            await asyncio.sleep(poll_s)

        # Always fetch result to clear job (ack+pop)
        result = await self.call_tool("get_job_result", {"job_id": job_id, "token": token})
        payload = getattr(result, "data", None) or {}

        state = payload.get("state")
        if state == "done":
            return result

        raise RuntimeError(
            f"Long tool {tool_name} job {job_id} ended with {state}: {payload.get('error')}"
        )

    async def _throttle(self, *, min_interval_s: float, jitter_s: float) -> None:
        """Ensure at least min_interval_s between tool calls (plus jitter)."""
        now = time.monotonic()
        wait = max(0.0, self._next_allowed_ts - now)
        wait += random.uniform(0.0, jitter_s)
        if wait > 0:
            await asyncio.sleep(wait)
        self._next_allowed_ts = time.monotonic() + min_interval_s

    async def call_tools_polite(
        self,
        tool_name: str,
        args: dict,
        *,
        min_interval_s: float = 2.5,
        jitter_s: float = 1.5,
        max_retries: int = 4,
        base_backoff_s: float = 15.0,
    ):
        """Call a tool with throttling + exponential backoff on transient blocks."""
        attempt = 0
        while True:
            await self._throttle(min_interval_s=min_interval_s, jitter_s=jitter_s)
            try:
                if args.get("token") is None:
                    return await self.call_tool(tool_name, args)
                return await self.call_long_tool_and_get_result(tool_name, args)
            except Exception as e:
                msg = str(e).lower()
                transient = any(k in msg for k in ["429", "too many requests", "blocked", "requestblocked", "rate"])
                if (not transient) or (attempt >= max_retries):
                    raise
                sleep_s = base_backoff_s * (2 ** attempt) + random.uniform(0, 5)
                logger.warning(
                    "Transient error calling %s (attempt %s/%s): %s; sleeping %.1fs",
                    tool_name,
                    attempt + 1,
                    max_retries + 1,
                    e,
                    sleep_s,
                )
                await asyncio.sleep(sleep_s)
                attempt += 1
