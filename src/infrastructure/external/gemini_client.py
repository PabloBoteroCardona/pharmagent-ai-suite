"""Cliente para la API multimodal de Google Gemini (extracción de recetas).

Encapsula el acceso a Gemini (`google-genai`), usado exclusivamente por
`PrescriptionAgent` para comprensión multimodal de imágenes de recetas médicas.
`GOOGLE_API_KEY` (`settings.google_api_key`) está reservada a este cliente: nunca se usa
para embeddings ni RAG, que permanecen exclusivamente en Ollama local. Nunca propaga
excepciones: ante un fallo de red, API o parseo, degrada a
`{"drugs": [], "advertencias": []}` para que las capas superiores decidan cómo continuar.

Nota sobre el modelo: `gemini-1.5-pro` (usado originalmente, ver AGENTS.md/SKILLS.md)
ha sido retirado por Google — devuelve `404 NOT_FOUND` para cualquier API key nueva desde
esta sesión de evaluación (BLOQUE D, ver EVALUATION.md). Se sustituyó por
`gemini-flash-latest`, un alias siempre apuntando al modelo Flash estable más reciente,
verificado multimodal contra imágenes reales de receta. `gemini-2.5-pro`/`gemini-2.0-flash`
también existen pero devolvieron `429 RESOURCE_EXHAUSTED` con la cuota gratuita disponible
en esta evaluación.
"""

from __future__ import annotations

import json

from google import genai
from google.genai import types
from google.genai.errors import APIError

from src.infrastructure.config.settings import settings

DEFAULT_MODEL = "gemini-flash-latest"

SYSTEM_PROMPT = (
    "Eres un asistente farmacéutico que transcribe recetas médicas con precisión clínica. "
    "Extrae de la imagen de la receta cada fármaco prescrito junto con su dosificación, "
    "frecuencia de administración y duración del tratamiento, además de cualquier "
    "advertencia relevante (alergias señaladas, condiciones especiales, indicaciones del "
    "prescriptor). Nunca inventes un fármaco, dosis o dato que no sea legible con certeza en "
    "la imagen; si un campo no es legible, devuélvelo como null. "
    "IMPORTANTE — protección de datos: no incluyas en ningún campo de la respuesta (ni "
    "siquiera en advertencias) el nombre del paciente, DNI/NIE, dirección, número de la "
    "seguridad social, ni ningún otro dato que identifique a una persona concreta, aunque "
    "sea legible en la imagen; extrae únicamente la información clínica del tratamiento "
    "(fármacos, dosis, pauta y advertencias clínicas). Responde EXCLUSIVAMENTE con "
    "un objeto JSON, sin texto adicional, con esta forma exacta: "
    '{"drugs": [{"farmaco": string, "dosificacion": string | null, '
    '"frecuencia": string | null, "duracion": string | null}], "advertencias": [string]}'
)

_EMPTY_RESULT: dict = {"drugs": [], "advertencias": []}


class GeminiClient:
    """Cliente de Gemini para análisis multimodal de recetas médicas."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        resolved_key = api_key or settings.google_api_key
        self._client = genai.Client(api_key=resolved_key) if resolved_key else None
        self._model = model

    async def analyze_prescription_image(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> dict:
        """Envía la imagen a Gemini y devuelve el JSON estructurado de la receta."""
        if self._client is None:
            return dict(_EMPTY_RESULT)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    SYSTEM_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            data = json.loads(response.text or "{}")
        except (APIError, json.JSONDecodeError, ValueError):
            return dict(_EMPTY_RESULT)

        if not isinstance(data, dict):
            return dict(_EMPTY_RESULT)

        return {
            "drugs": data.get("drugs", []),
            "advertencias": data.get("advertencias", []),
        }
