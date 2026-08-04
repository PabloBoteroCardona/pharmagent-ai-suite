"""Punto de entrada de la API REST de PharmAgent AI Suite."""

from __future__ import annotations

import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.infrastructure.api.routers.pharmacy_router import router as pharmacy_router
from src.infrastructure.config.settings import settings

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=1.0,
    )

app = FastAPI(title="PharmAgent AI Suite API")
app.include_router(pharmacy_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
