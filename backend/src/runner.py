"""
Multi-tenant entry point.

Starts:
1. ``MarketDataScanner``         — single shared thread, public market data
2. ``BotOrchestrator``           — per-user worker pool
3. ``FastAPI`` server (uvicorn)  — REST + WebSocket on the API port

Run with:  ``python src/runner.py``
"""

from __future__ import annotations

import os
import signal
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.api.deps import get_vault
from src.bot.orchestrator import BotOrchestrator
from src.bot.scanner import MarketDataScanner
from src.monitoring.logger import get_logger


log = get_logger()


def _start_api_server(scanner: MarketDataScanner, orchestrator: BotOrchestrator):
    """Launch FastAPI/uvicorn in a daemon thread."""
    import uvicorn
    from src.api.main import create_app

    app = create_app(scanner=scanner, orchestrator=orchestrator)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.API_PORT,
        log_level="warning",
    )


def main():
    log.info("Starting CrypSavvy multi-tenant bot")

    vault = get_vault()
    scanner = MarketDataScanner()
    orchestrator = BotOrchestrator(scanner=scanner, vault=vault)

    scanner.start()
    log.info(f"API server starting on port {settings.API_PORT}")

    api_thread = threading.Thread(
        target=_start_api_server,
        args=(scanner, orchestrator),
        daemon=True,
        name="api-server",
    )
    api_thread.start()

    # Resume bots for users that had bot_enabled=true at last shutdown
    orchestrator.boot_persisted_users()

    stop_event = threading.Event()

    def _stop(signum, frame):
        log.info("Shutdown signal received — stopping orchestrator + scanner")
        for user_id in list(orchestrator.all_states().keys()):
            try:
                orchestrator.stop(user_id)
            except Exception:
                log.exception(f"Failed to stop bot for {user_id}")
        scanner.stop()
        stop_event.set()

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    stop_event.wait()
    log.info("Bot stopped.")


if __name__ == "__main__":
    main()
