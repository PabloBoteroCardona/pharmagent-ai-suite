"""Punto de entrada de la API REST de PharmAgent."""

from __future__ import annotations

import sentry_sdk
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure import metrics
from src.infrastructure.api.routers.pharmacy_router import router as pharmacy_router
from src.infrastructure.api.security import verify_api_key
from src.infrastructure.config.settings import settings
from src.infrastructure.logging_config import configure_logging

configure_logging()

# Tamaño máximo de cuerpo de petición (recetas fotografiadas con el móvil caben de sobra;
# protege de subidas descontroladas — abuso de ancho de banda/memoria, y de coste en Gemini
# si la API queda expuesta públicamente). Se comprueba por `Content-Length` antes de leer el
# cuerpo, sin cargarlo en memoria solo para medirlo.
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": (
                        "Cuerpo de la petición demasiado grande "
                        f"(máximo {MAX_REQUEST_BODY_BYTES // (1024 * 1024)} MB)."
                    )
                },
            )
        return await call_next(request)


if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=1.0,
    )

app = FastAPI(title="PharmAgent API")

# Rate limiting por IP (`settings.rate_limit`, ver security.py/pharmacy_router.py para la
# autenticación opcional que lo complementa) — protege de abuso/coste descontrolado en
# Groq/Gemini si la API se expone públicamente. `/health` queda exenta explícitamente para
# no interferir con los chequeos de salud del proveedor de despliegue.
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(MaxBodySizeMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pharmacy_router)


@app.get("/health")
@limiter.exempt
async def health(request: Request) -> dict:
    return {"status": "ok"}


@app.get("/internal/metrics", dependencies=[Depends(verify_api_key)])
@limiter.exempt
async def internal_metrics(request: Request) -> dict:
    """Latencia p50/p95 por proveedor LLM y tasa de fallback a CIMA en vivo (ver
    `metrics.py`) — snapshot en memoria, se reinicia con cada reinicio del proceso.
    Sujeto a `API_KEY` cuando está configurada (igual que `pharmacy_router`, ver
    `security.py`), exento de rate limiting: es un endpoint de diagnóstico, no de negocio,
    pensado para sondearse con más frecuencia de la que `RATE_LIMIT` permitiría."""
    return metrics.snapshot()
