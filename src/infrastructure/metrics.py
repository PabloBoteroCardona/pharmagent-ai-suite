"""Métricas básicas en memoria: latencia por proveedor LLM y tasa de fallback a CIMA en vivo.

Deliberadamente simple (sin Prometheus/StatsD ni backend externo) — cierra la brecha de "no
hay visibilidad de latencia/errores de los proveedores LLM" con lo mínimo razonable para el
tamaño de este proyecto: un snapshot en memoria, expuesto en `GET /internal/metrics` (ver
`main.py`). Se reinicia en cada reinicio del proceso y no se comparte entre réplicas — no
pretende sustituir un sistema de observabilidad real (Prometheus/Grafana) en un servicio con
tráfico de producción y más de una instancia.

Tratado como una utilidad de infraestructura sin estado de negocio, en la misma categoría
que el logging (`logging_config.py`): se llama desde `application/services/drug_service.py`
igual que se llamaría a un logger, no a través de un puerto de dominio — no es una
dependencia de reglas de negocio, es observabilidad transversal.
"""

from __future__ import annotations

import functools
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

# Ventana acotada por proveedor: suficiente para un p50/p95 representativo reciente sin
# crecer sin límite en un proceso de larga duración.
MAX_SAMPLES_PER_PROVIDER = 500

_latencies_ms: dict[str, deque[float]] = {}
_cima_search_outcomes: dict[str, int] = {"cache": 0, "live": 0, "none": 0}


def record_latency(provider: str, elapsed_ms: float) -> None:
    samples = _latencies_ms.setdefault(provider, deque(maxlen=MAX_SAMPLES_PER_PROVIDER))
    samples.append(elapsed_ms)


def record_cima_search_outcome(source: str) -> None:
    """`source` es el mismo valor que ya devuelve `DrugService.search_drugs_semantic`
    (`DrugSearchResult.source`): `"cache"`, `"live"` o `"none"`."""
    if source in _cima_search_outcomes:
        _cima_search_outcomes[source] += 1


def timed(
    provider: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorador: mide la latencia total (incluyendo reintentos, ver `retry.py`) de una
    llamada async a un proveedor externo y la registra bajo `provider`."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            start = time.monotonic()
            try:
                return await func(*args, **kwargs)
            finally:
                record_latency(provider, (time.monotonic() - start) * 1000)

        return wrapper

    return decorator


def _percentile(ordered_samples: list[float], percentile: float) -> float | None:
    if not ordered_samples:
        return None
    index = min(int(len(ordered_samples) * percentile), len(ordered_samples) - 1)
    return round(ordered_samples[index], 1)


def snapshot() -> dict:
    """Estado actual de las métricas — serializado tal cual por `GET /internal/metrics`."""
    latency_by_provider = {}
    for provider, samples in _latencies_ms.items():
        ordered = sorted(samples)
        latency_by_provider[provider] = {
            "count": len(ordered),
            "p50_ms": _percentile(ordered, 0.50),
            "p95_ms": _percentile(ordered, 0.95),
        }

    total_searches = sum(_cima_search_outcomes.values())
    live_fallback_rate = (
        round(_cima_search_outcomes["live"] / total_searches, 3)
        if total_searches
        else None
    )

    return {
        "latency_by_provider_ms": latency_by_provider,
        "cima_search": {
            "outcomes": dict(_cima_search_outcomes),
            "live_fallback_rate": live_fallback_rate,
        },
    }
