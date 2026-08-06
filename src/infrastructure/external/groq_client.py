"""Cliente HTTP asíncrono para la API de inferencia ultrarrápida de Groq.

Sustituye a Ollama local (CPU) como motor de generación de texto para `RAGPharmAgent` y
`SafetyCheckAgent` — la generación en CPU local tardaba ~30s por respuesta (arranque en
frío incluido, ver BUGS.md); Groq ejecuta sobre LPUs dedicadas y responde en <2s para el
mismo tipo de prompt corto. Los embeddings NO pasan por este cliente: siguen
exclusivamente en `OllamaClient` local por la política de privacidad de datos de salud de
`settings.py` — Groq tampoco ofrece una API de embeddings, así que `generate_embedding`
aquí es un stub inerte que nunca se invoca en la práctica (ver cableado de dependencias en
`pharmacy_router.py`: `DrugService` sigue recibiendo `OllamaClient`, no este cliente).
Nunca propaga excepciones de red: ante la ausencia de API key, un fallo de conexión,
timeout, respuesta de error o cuerpo malformado, degrada a `""` (mismo contrato que
`OllamaClient.generate_completion`) para que las capas superiores decidan cómo continuar.
"""

from __future__ import annotations

import json
import logging
from typing import Self

import httpx

from src.infrastructure.config.settings import settings
from src.infrastructure.external.retry import retry_transient_errors
from src.infrastructure.metrics import timed

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_COMPLETION_MODEL = "llama-3.1-8b-instant"


class GroqClient:
    """Cliente de la API de Groq (chat completions, compatible con el esquema de OpenAI)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.groq_api_key
        self._model = model or settings.groq_model or DEFAULT_COMPLETION_MODEL
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.groq_base_url, timeout=timeout
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate_embedding(self, text: str) -> list[float]:
        """No soportado: Groq no ofrece una API de embeddings. Los embeddings permanecen
        en `OllamaClient` local (ver docstring del módulo) — este método existe solo para
        satisfacer estructuralmente `LanguageModelPort` y nunca se invoca en la práctica."""
        return []

    @timed("groq")
    @retry_transient_errors
    async def generate_completion(
        self,
        prompt: str,
        system: str = "",
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Genera texto con Groq. Devuelve `""` si no hay API key configurada, o si falla
        la conexión, la API o el parseo de la respuesta.

        `temperature`: por defecto Groq usa su propio valor por omisión (muestreo, no
        determinista) si no se especifica. Los llamadores que devuelven datos de seguridad
        clínica (`SafetyCheckAgent`, `RAGPharmAgent`) deben fijarlo a `0.0` explícitamente —
        una respuesta de interacciones farmacológicas no puede variar entre peticiones
        idénticas."""
        if not self._api_key:
            return ""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": model or self._model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            response = await self._client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            return choices[0]["message"]["content"] if choices else ""
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.warning("groq_generate_completion_failed", extra={"error": str(exc)})
            return ""
