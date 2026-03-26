"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI

try:
    from .routes.projects import router as projects_router
    from .routes.quotations import router as quotations_router
    from .routes.shops import router as shops_router
except ImportError:
    from routes.projects import router as projects_router
    from routes.quotations import router as quotations_router
    from routes.shops import router as shops_router


def create_app() -> FastAPI:
    app: FastAPI = FastAPI(title="DataManager Gateway Mock", version="0.1.0")
    app.include_router(shops_router)
    app.include_router(projects_router)
    app.include_router(quotations_router)
    return app
