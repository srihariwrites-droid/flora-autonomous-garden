"""Flora entry point: load config, init DB, start scheduler and dashboard."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

from flora.config import load_config
from flora.db import Database
from flora.scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def _main(config_path: str) -> None:
    config = load_config(config_path)
    db = Database(config.db_path)
    await db.connect()
    logger.info("Database connected at %s", config.db_path)

    scheduler = create_scheduler(config, db)
    scheduler.start()
    logger.info("Scheduler started")

    # Import here to avoid circular at module level
    from flora.dashboard.app import create_app
    app = create_app(config, db)

    server_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.dashboard_port,
        log_level="warning",
    )
    server = uvicorn.Server(server_config)
    logger.info("Dashboard starting on http://0.0.0.0:%d", config.dashboard_port)

    try:
        await server.serve()
    finally:
        scheduler.shutdown(wait=False)
        await db.close()
        logger.info("Flora shut down cleanly")


def cli() -> None:
    """Entry point for `flora` CLI command."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "flora.toml"
    if not Path(config_path).exists():
        print(f"Config not found: {config_path}")
        print("Copy flora.example.toml to flora.toml and fill in your values.")
        sys.exit(1)
    asyncio.run(_main(config_path))


if __name__ == "__main__":
    cli()
