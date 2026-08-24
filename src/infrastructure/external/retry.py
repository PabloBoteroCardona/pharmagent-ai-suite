"""Reintentos con backoff exponencial para clientes HTTP externos (CIMA, Groq, Ollama,
Gemini).

Solo reintenta fallos transitorios — error de red/timeout, 429 (rate limit) o 5xx del
proveedor — nunca un 4xx de validación (payload incorrecto, no autorizado, etc.): esos no
se arreglan reintentando la misma petición. `reraise=True` conserva el contrato defensivo
que ya tenía cada cliente: tras agotar los intentos, se relanza la excepción original para
que el `except (httpx.HTTPError, ...)` de cada método siga degradando exactamente igual
que antes de añadir reintentos.
"""

from __future__ import annotations

import httpx
import requests
from google.genai.errors import APIError as GenAIAPIError
from google.genai.errors import ClientError as GenAIClientError
from google.genai.errors import ServerError as GenAIServerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}

RETRY_ATTEMPTS = 3
RETRY_WAIT_MULTIPLIER_SECONDS = 0.5
RETRY_WAIT_MAX_SECONDS = 4


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(exc, httpx.TransportError):
        return True
    # `google-genai` usa `requests` (no httpx) para sus llamadas HTTP internas — un timeout o
    # fallo de conexión ahí nunca llega a envolverse en GenAIServerError/GenAIAPIError (esos
    # solo aplican cuando sí hubo respuesta HTTP). Bug real en producción: sin esto,
    # `requests.exceptions.ReadTimeout` no se reintentaba y se propagaba sin capturar (500).
    if isinstance(
        exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
    ):
        return True
    if isinstance(exc, GenAIServerError):
        return True
    if isinstance(exc, GenAIClientError):
        return exc.code == 429
    return isinstance(exc, GenAIAPIError) and exc.code in RETRYABLE_HTTP_STATUS_CODES


retry_transient_errors = retry(
    retry=retry_if_exception(_is_transient_error),
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=RETRY_WAIT_MULTIPLIER_SECONDS, max=RETRY_WAIT_MAX_SECONDS
    ),
    reraise=True,
)
