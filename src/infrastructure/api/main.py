"""Punto de entrada de la API REST de PharmAgent AI Suite."""

from __future__ import annotations

from fastapi import FastAPI

from src.infrastructure.api.routers.pharmacy_router import router as pharmacy_router

app = FastAPI(title="PharmAgent AI Suite API")
app.include_router(pharmacy_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
