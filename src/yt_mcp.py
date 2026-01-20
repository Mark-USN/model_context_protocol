""" 20251010 MMH model_context_protocol.py
    A driver program to start/stop a detached MCP server or run a client. 

    USAGE: model_context_protocol.py --mode server|client|stop-server, 
                [--host HOST] [--port PORT] [--debug True/False]
    Parameters:
        --mode: "server" to start a detached server, "client" to run a client,
                "stop-server" to stop a detached server.
        --host: Hostname or IP address (default 127.0.0.1)
        --port: TCP port number (default 8085)
        --debug: If True, launch server as child process; if False, launch
                 as detached process (default False)
"""

import sys
import os
import shutil
import argparse
import asyncio
import subprocess
import signal
import logging
from modules.utils.logging_config import setup_logging
from pathlib import Path
from modules.mcp_servers import demo_server, long_job_server
from modules.mcp_clients.universal_client import UniversalClient

# -----------------------------
# Logging setup
# -----------------------------
setup_logging()
logger = logging.getLogger(__name__)


# -----------------------------
# Paths (PID & LOG live next to this file)
# -----------------------------
SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent.resolve()
PID_FILE = ROOT_DIR / "cache" / "mcp.pid"
LOG_FILE = ROOT_DIR / "cache" / "mcp.log"


# ---- Helper to find pythonw.exe on Windows ----
# On Windows, we want to use pythonw.exe to avoid a console window popping up.
def _pythonw_exe():
    """ 20251101 MMH _pythonw_exe
        Return the path to pythonw.exe if on Windows, else sys.executable.
        This is the python interpreter used to launch the detached server process. 
        On Windows, we prefer pythonw.exe to avoid a console window.
    """
    # Prefer side-by-side pythonw next to the current interpreter
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        candidate = exe[:-10] + "pythonw.exe"
        if os.path.exists(candidate):
            return candidate
    # Fallback to PATH
    return shutil.which("pythonw.exe") or exe  # last resort: python.exe


# ---- Background launcher (detached subprocess) ----
def start_server(host: str, port: int, debug: bool, mode:str):
    """ 20251101 MMH start_server
        Launches the MCP server as either a child process or as a detached process,
        depending on the debug flag. False will launch a detached process.
        20251214 MMH: Added mode parameter to select between demo_server and long_job_server.
    """

    if debug:
        # Launch the server in the current process (foreground) for debugging.
        if mode == "server":
            demo_server.launch_server(host, port)
        else:
            long_job_server.launch_server(host, port)
        return

    # --- Detached mode ---
    # Command line to run the server module

    cmd_str = ("modules.mcp_servers.demo_server" if mode == "server" else "modules.mcp_servers.long_job_server")
    

    cmd = [
        _pythonw_exe(),
        "-m",
        cmd_str,
        "--host", host,
        "--port", str(port),
    ]

    # Platform-specific detachment options
    kwargs: dict = {}
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS 
        # flags = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS 
            # subprocess.CREATE_NO_WINDOW
        
        kwargs["creationflags"] = flags
        # NOTE: no close_fds here on Windows, because of redirected std handles
    else:
        kwargs["preexec_fn"] = os.setpgrp  # pylint: disable=no-member
        kwargs["close_fds"] = True
    
    # 20251204 MMH: Ensure log file and pid file exist
    if not LOG_FILE.parent.exists():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.touch(exist_ok=True)
    if not PID_FILE.parent.exists():
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.touch(exist_ok=True)

    # Use `with` for the log file only; the server keeps running after this
    # script exits.
    logger.info("✅ %s started (detached) on http://%s:%i.", cmd_str, host, port)

    with open(LOG_FILE, "a",
              buffering=1,
              encoding="utf-8",
              errors="replace") as log_fh:
        # pylint: disable=consider-using-with
        proc = subprocess.Popen(        
            cmd,
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
            cwd=str(SRC_DIR),
            **kwargs,
        )

    # At this point:
    #   - Child process is running independently
    #   - log_fh is closed in the parent (child still has its own handles)
    #   - We only keep and record the PID
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    logger.info("✅ Server started (detached) on http://%s:%i.", host, port)
    logger.info("ℹ    PID: %i.", proc.pid)
    logger.info("ℹ    Log: %s.", LOG_FILE)


def stop_server():
    """ 20251101 MMH stop_server
        Stop a previously started detached server using the PID file.
    """
    if not PID_FILE.exists():
        logger.error("🛑	 No PID file found; server may not be running.")
        return

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        logger.error("🛑	 No PID file found; server may not be running.")
        return

    if pid <= 0:
        logger.error("🛑	 No PID file found; server may not be running.")
        return

    # Try to terminate cross-platform
    try:
        if os.name == "nt":
            # Use taskkill to terminate the process tree reliably on Windows
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           check=True, capture_output=True, text=True)
        else:
            os.kill(pid, signal.SIGTERM)
            logger.info("ℹ Sent stop signal to PID %i.", pid)
    except ProcessLookupError as e:
        logger.error("🛑 Process %i not found.", pid)
        raise SystemExit(f"🛑 Process {pid} not found.  Error = {e}") from e



    # Clean up PID file regardless (best-effort)
    # Remove the old PID files if present
    PID_FILE.unlink(missing_ok=True)


def port_type(value: str) -> int:
    """ 20251101 MMH port_type
        Custom argparse type that validates a TCP port number.
    """
    try:
        port = int(value)
    except ValueError as e:
        logger.error("❌ Port must be an integer.\n%s Port = %s.",
            str(value), e)
        raise SystemExit(f"❌ Port must be an integer.\n{value} Port = {e}") from e
    if not 1 <= port <= 65535:
        logger.error("❌ Port number must be between 1 and 65535 (got {port!r})")
        raise SystemExit(
            f"Port number must be between 1 and 65535!. Port = {port}.") from e
    return port

def main():
    """ Main entry point: parse arguments and start/stop server or run client. """    
    parser = argparse.ArgumentParser(
        description="Create and run an MCP server or client."
    )

    parser.add_argument("--mode",
        choices=["server", "client", "stop-server","long-job-server"],
        type=str.lower,
        required=True,
        help="Run as server, long_job_server, client, or stop-server."
    )

    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085,
                        help="TCP port to bind/connect (default 8085).")
    parser.add_argument("--debug", action="store_true",
                        help="Lauch the server as a child of this Process "
                        "(True) or as a seperate Process (False).\n The "
                        "default is False")
    args = parser.parse_args()

    # 20251215 MMH Show help if no arguments are given
    if len(sys.argv) == 1:  
        parser.print_help()
        sys.exit(1)  # Exit with an error code

    if args.mode == "server":
        # Parent: launch a detached child and return immediately
        start_server(args.host, args.port, args.debug, args.mode)
        # Parent exits now; detached child continues running.

    elif args.mode == "stop-server":
        stop_server()

    elif args.mode == "client":
        client = UniversalClient(args.host, args.port)
        asyncio.run(client.run())
    
    elif args.mode == "long-job-server":
        # Parent: launch a detached child and return immediately
        start_server(args.host, args.port, args.debug, args.mode)
        # Parent exits now; detached child continues running.


if __name__ == "__main__":
    # If run as a script, execute main().
    main()
