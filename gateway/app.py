"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI
from routes.auto import router as auto_router
from routes.shop import router as shop_router


def create_app() -> FastAPI:
    app: FastAPI = FastAPI(title="DataManager Gateway", version="0.1.0")
    app.include_router(auto_router)
    app.include_router(shop_router)
    return app
