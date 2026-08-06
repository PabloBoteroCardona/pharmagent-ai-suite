"""Logging estructurado (JSON) para toda la aplicación.

Configura el logger raíz para emitir cada línea como un objeto JSON (timestamp, nivel,
logger, mensaje, más los campos `extra` de cada llamada) en vez de texto plano. Necesario
para poder buscar o alertar sobre fallos concretos (p. ej. "todas las llamadas a Groq
fallando") una vez desplegado, donde no hay una terminal que mirar en directo — un
proveedor de despliegue (Render) recoge stdout y lo indexa como texto; JSON por línea es lo
mínimo para que eso sea consultable. Se llama una única vez, al importar `main.py`.
"""

from __future__ import annotations

import logging

from pythonjsonlogger.json import JsonFormatter


def configure_logging(level: int = logging.INFO) -> None:
    """Sustituye los handlers del logger raíz por uno que emite JSON a stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
