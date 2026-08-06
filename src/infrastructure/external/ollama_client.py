"""Cliente HTTP asíncrono para un servidor Ollama local.

Encapsula el acceso a la API de Ollama (`{settings.ollama_base_url}/api/...`)
usada por `SafetyCheckAgent` y `RAGPharmAgent` para generación local (Llama 3.1,
Gemma 2) y embeddings. Nunca propaga excepciones de red: ante un fallo de
conexión, timeout, respuesta de error o cuerpo malformado, degrada a una
estructura vacía (`[]` / `""`) para que las capas superiores decidan cómo
continuar.
"""

from __future__ import annotations

import json
from typing import Self

import httpx

from src.infrastructure.config.settings import settings

# La generación local puede tardar bastante más que una simple consulta REST;
# un timeout demasiado corto produciría fallos espurios en modelos grandes.
DEFAULT_TIMEOUT_SECONDS = 60.0

DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_COMPLETION_MODEL = "llama3"


class OllamaClient:
    """Cliente del servidor Ollama local (embeddings y generación de texto)."""

    def __init__(
        self, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.ollama_base_url, timeout=timeout
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate_embedding(
        self, text: str, model: str = DEFAULT_EMBEDDING_MODEL
    ) -> list[float]:
        """Genera el embedding de `text`. Devuelve `[]` si falla la conexión o Ollama no está disponible."""
        try:
            response = await self._client.post(
                "/api/embeddings", json={"model": model, "prompt": text}
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except (httpx.HTTPError, json.JSONDecodeError):
            return []

    async def generate_completion(
        self,
        prompt: str,
        system: str = "",
        model: str = DEFAULT_COMPLETION_MODEL,
        temperature: float | None = None,
    ) -> str:
        """Genera texto a partir de `prompt`. Devuelve `""` si falla la conexión o Ollama no está disponible."""
        payload: dict[str, object] = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
        }
        if temperature is not None:
            payload["options"] = {"temperature": temperature}

        try:
            response = await self._client.post("/api/generate", json=payload)
            response.raise_for_status()
            return response.json().get("response", "")
        except (httpx.HTTPError, json.JSONDecodeError):
            return ""
