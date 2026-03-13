"""FastAPI application factory for the Flora dashboard."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from flora.config import AppConfig
from flora.db import Database
from flora.dashboard.routes import create_router

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(config: AppConfig, db: Database) -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(title="Flora Dashboard", docs_url=None, redoc_url=None)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    router = create_router(config, db, templates)
    app.include_router(router)

    return app
