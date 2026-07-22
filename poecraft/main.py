"""PoECraft — Main entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from poecraft.config import get_config, load_config
from poecraft.web.routes import router as web_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("poecraft")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: load config on startup."""
    config = get_config()
    logger.info("PoECraft starting — league=%s, tabs=%s", config.league, config.stash_tabs)
    yield
    logger.info("PoECraft shutting down")


app = FastAPI(title="PoECraft", lifespan=lifespan)
app.include_router(web_router)


def cli():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="PoECraft — Chaos Recipe Filter Tool")
    parser.add_argument("--config", "-c", help="Path to config.yaml")
    parser.add_argument("--host", help="Bind host (default: from config)")
    parser.add_argument("--port", type=int, help="Bind port (default: from config)")
    args = parser.parse_args()

    config = load_config(args.config)
    host = args.host or config.host
    port = args.port or config.port

    logger.info("Starting server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli()
