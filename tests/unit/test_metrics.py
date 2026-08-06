"""Tests unitarios de `metrics.py`: percentiles, tasa de fallback CIMA y el decorador
`timed`. Cada test resetea el estado global del módulo (ver fixture `_reset_metrics`) — sin
eso, los contadores en memoria se acumularían entre tests y los resultados dependerían del
orden de ejecución.
"""

from __future__ import annotations

import asyncio

import pytest

from src.infrastructure import metrics


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    metrics._latencies_ms.clear()
    metrics._cima_search_outcomes.update(cache=0, live=0, none=0)


class TestRecordLatencyAndSnapshot:
    def test_snapshot_omits_providers_with_no_samples(self) -> None:
        assert metrics.snapshot()["latency_by_provider_ms"] == {}

    def test_records_count_and_percentiles_for_a_provider(self) -> None:
        for value in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            metrics.record_latency("groq", value)

        result = metrics.snapshot()["latency_by_provider_ms"]["groq"]

        assert result["count"] == 10
        assert result["p50_ms"] == 60
        assert result["p95_ms"] == 100

    def test_keeps_providers_independent(self) -> None:
        metrics.record_latency("groq", 5)
        metrics.record_latency("gemini", 500)

        result = metrics.snapshot()["latency_by_provider_ms"]

        assert result["groq"]["p50_ms"] == 5
        assert result["gemini"]["p50_ms"] == 500

    def test_bounds_samples_per_provider(self) -> None:
        for value in range(metrics.MAX_SAMPLES_PER_PROVIDER + 50):
            metrics.record_latency("groq", value)

        assert metrics.snapshot()["latency_by_provider_ms"]["groq"]["count"] == (
            metrics.MAX_SAMPLES_PER_PROVIDER
        )


class TestCimaSearchOutcome:
    def test_reports_none_fallback_rate_without_any_search(self) -> None:
        assert metrics.snapshot()["cima_search"]["live_fallback_rate"] is None

    def test_computes_live_fallback_rate_across_outcomes(self) -> None:
        metrics.record_cima_search_outcome("cache")
        metrics.record_cima_search_outcome("cache")
        metrics.record_cima_search_outcome("live")
        metrics.record_cima_search_outcome("none")

        result = metrics.snapshot()["cima_search"]

        assert result["outcomes"] == {"cache": 2, "live": 1, "none": 1}
        assert result["live_fallback_rate"] == 0.25

    def test_ignores_unknown_outcome_values(self) -> None:
        metrics.record_cima_search_outcome("not-a-real-outcome")

        assert metrics.snapshot()["cima_search"]["outcomes"] == {
            "cache": 0,
            "live": 0,
            "none": 0,
        }


class TestTimedDecorator:
    @pytest.mark.asyncio
    async def test_records_latency_of_a_successful_call(self) -> None:
        @metrics.timed("test-provider")
        async def fast_call() -> str:
            await asyncio.sleep(0)
            return "ok"

        result = await fast_call()

        assert result == "ok"
        assert (
            metrics.snapshot()["latency_by_provider_ms"]["test-provider"]["count"] == 1
        )

    @pytest.mark.asyncio
    async def test_records_latency_even_when_the_call_raises(self) -> None:
        @metrics.timed("test-provider")
        async def failing_call() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await failing_call()

        assert (
            metrics.snapshot()["latency_by_provider_ms"]["test-provider"]["count"] == 1
        )
