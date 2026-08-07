"""Enforcement en el backend del modo demo (`settings.demo_mode`).

En el despliegue público, el frontend restringe la pestaña de Receta a los 3 ejemplos
sintéticos de `frontend/public/samples/` en vez de aceptar fotos reales (ver ADR 002,
`viewPrescription.ts`) — pero eso por sí solo es un enforcement solo de cliente: cualquiera
puede seguir llamando a `/analyze-prescription`/`/process-prescription` directamente con
una foto real, sin pasar por la UI. Este módulo cierra esa brecha comprobando el hash
SHA-256 del cuerpo subido contra el de los 3 ejemplos conocidos — con el modo demo activo,
nunca se acepta una imagen que no sea exactamente uno de esos 3 archivos.

Los hashes deben regenerarse (`hashlib.sha256(contenido).hexdigest()`) si se sustituyen las
imágenes de `frontend/public/samples/`.
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException

ALLOWED_DEMO_IMAGE_SHA256 = {
    "aed0689cce7c4bd36ef97dcda63763e409428291bc213cab732b1c690f004a65",
    "dea0e05157d49fa0163252fe5d5b70f79497d8d603551fba00f596ade07cf778",
    "f8079bb882b127d54c27f2b84c6a04ea635620395201cac52e50a8199b92c523",
}


def enforce_demo_mode_allowlist(image_bytes: bytes) -> None:
    """Lanza `HTTPException(403)` si la imagen subida no es uno de los ejemplos permitidos.

    Solo debe llamarse cuando `settings.demo_mode` está activo (ver `pharmacy_router.py`).
    """
    if hashlib.sha256(image_bytes).hexdigest() not in ALLOWED_DEMO_IMAGE_SHA256:
        raise HTTPException(
            status_code=403,
            detail=(
                "Modo demo activo: esta instancia pública solo procesa las imágenes de "
                "ejemplo incluidas en la aplicación, no fotos reales. Ejecuta el proyecto "
                "en local (VITE_DEMO_MODE sin activar) para subir una receta propia."
            ),
        )
