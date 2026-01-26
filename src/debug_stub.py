#./src/debug_stub.py

# import signal
import asyncio
import logging
import argparse
import sys
from modules.utils.log_utils import configure_logging, get_logger

# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)


def debug_stub():
    """ Main entry point: parse arguments and start/stop server or run client. """    
    parser = argparse.ArgumentParser(
        description="Create and run an MCP server or client."
    )

    parser.add_argument("--test",
        choices=["demo-server", "long-job-server", "universal-client", "yt-search", "yt-audio"],
        type=str.lower,
        required=True,
        help="Run as server, long_job_server, client, or stop-server."
    )

    args = parser.parse_args()

    # 20251215 MMH Show help if no arguments are given
    if len(sys.argv) == 1:  
        parser.print_help()
        sys.exit(1)  # Exit with an error code

    match args.test:
        case "demo-server":
            import modules.mcp_servers.demo_server as demo
            demo.main()
        case "long-job-server":
            import modules.mcp_servers.long_job_server as ljs
            ljs.launch_server()
        case "universal-client":
            from modules.mcp_clients.universal_client import UniversalClient
            # import modules.mcp_clients.universal_client as uc
            asyncio.run(UniversalClient("127.0.0.1", 8085).run())
        case "yt_search":
            import modules.tools.youtube_search as yt_search
            # from modules.utils.api_keys import api_vault
            # api_keys = api_vault()
            # google_key = api_keys.get_value("GOOGLE_KEY")
            yt_search.main()
        case "yt-audio":
            import modules.tools.youtube_audio_transcript as yt_audio
            yt_audio.main()

if __name__ == "__main__":
    # -----------------------------
    # Logging setup
    # -----------------------------
    configure_logging()

    debug_stub()
