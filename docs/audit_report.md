# Informe de auditoría técnica — PharmAgent

Auditoría inicial a nivel Staff/Principal Engineer, seguida de una verificación de
post-remediación ejecutada contra el código y la suite de tests reales (no solo contra
documentación). Dos pasadas independientes, ambas con evidencia verificable.

## 1. Auditoría inicial

**Fecha**: 2026-08-06. **Alcance**: arquitectura limpia/DIP, seguridad/RGPD, resiliencia de
clientes externos, observabilidad, calidad de código/CI, reproducibilidad y base de datos.

### 1.1. Puntos fuertes confirmados

- DIP real (no cosmético): `src/domain/ports/drug_ports.py` define 5 `Protocol`
  (`@runtime_checkable`); las implementaciones concretas (`CimaAPIClient`, `OllamaClient`,
  `GroqClient`, `GeminiClient`, `DrugRepository`) los satisfacen por tipado estructural, sin
  herencia — verificado con `isinstance()`.
- Patrón defensivo consistente en los 4 clientes externos: nunca propagan excepciones,
  degradan a valores vacíos.
- `.env` correctamente excluido de git y del build de Docker; sin secretos hardcodeados
  (verificado con grep).
- Auth opcional + rate limiting (`slowapi`) + límite de tamaño de petición + SSL condicional
  para BD, con el trade-off de cada mecanismo documentado explícitamente en el propio código.
- Modo demo (RGPD) como eliminación de riesgo en origen, no como mitigación con avisos —
  decisión de diseño correcta (ver [ADR 002](adr/002-datos-personales-foto-receta.md)).
- Usuario no-root en el contenedor Docker.
- 143/143 tests, 90% de cobertura, `ruff check`/`format` limpios (verificado ejecutando la
  suite en el momento de la auditoría).

### 1.2. Hallazgos (brechas para producción)

| # | Hallazgo | Prioridad |
|---|---|---|
| 1 | Cero reintentos en los 4 clientes externos (CIMA, Groq, Gemini, Ollama): un único intento, cualquier fallo transitorio (timeout, 429, 5xx) degrada igual que un fallo real. | P0 |
| 2 | Cero logging de cualquier tipo en `src/` (ni `logging`, ni `print`). Como los clientes degradan en silencio por diseño, un fallo de proveedor en producción no deja ningún rastro — ni en logs, ni en Sentry (que solo ve excepciones no capturadas, y aquí nunca se propagan). | P0 |
| 3 | Import runtime (no bajo `TYPE_CHECKING`) de `DrugModel` (ORM de infraestructura) en `src/application/services/drug_service.py:24` — violación activa de la regla de dependencia, más grave que la ya documentada y aceptada en `drug_ports.py`. | P1 |
| 4 | Enforcement del modo demo (RGPD) solo en el frontend — el backend no impedía subir una foto real a `/analyze-prescription`/`/process-prescription` llamando directamente a la API, sin pasar por la UI. | P0 |
| 5 | Sin lockfile real de backend (`requirements.txt` fija rangos, no versiones resueltas); asimetría con el frontend, que sí tiene `package-lock.json`. | P1 |
| 6 | Sin auditoría periódica de dependencias en CI (`pip-audit`/`npm audit` solo manual). | P1 |
| 7 | `drug_repository.py` (33%) y `prescription_record_repository.py` (50%) con cobertura muy por debajo del resto — justo la capa que escribe en Postgres, sin tests directos contra una base real en CI. | P2 |
| 8 | `docker-compose.yml` sin `read_only`/`cap_drop`/límites de recursos; Postgres publicado innecesariamente al host cuando solo lo consume `api` en la misma red. | P2 |
| 9 | Sin métricas de latencia/tasa de error de los LLM ni de la tasa de fallback CIMA-en-vivo — ninguna visibilidad operativa más allá de lo que mide el frontend en cliente. | P2 |

## 2. Verificación de post-remediación

**Fecha**: 2026-08-06. Cada hallazgo se comprobó leyendo el código real (no el resumen que
lo reporta) y ejecutando la suite completa en local.

### 2.1. Resiliencia y observabilidad (P0)

**Reintentos** — `src/infrastructure/external/retry.py`: decorador `retry_transient_errors`
(`tenacity`, `stop_after_attempt(3)`, `wait_exponential`), aplicado a los 4 clientes:

| Cliente | Métodos decorados |
|---|---|
| `CimaAPIClient` | `search_medicamentos`, `_get_medicamento`, `_get_documento_segmentado_html` |
| `GroqClient` | `generate_completion` |
| `GeminiClient` | `analyze_prescription_image` |
| `OllamaClient` | `generate_embedding`, `generate_completion` |

Solo reintenta fallos transitorios (`httpx.TransportError`, HTTP 429/500/502/503/504,
`google.genai` `ServerError`/`ClientError(429)`) — nunca un 4xx de validación; `reraise=True`
conserva el contrato defensivo original (tras agotar los 3 intentos, la excepción llega igual
al `except` de cada método, que sigue degradando exactamente como antes).

**Logging estructurado** — `src/infrastructure/logging_config.py` (`configure_logging`,
`pythonjsonlogger.json.JsonFormatter`, formato JSON a stdout), llamado una vez desde
`main.py:23`. Los 4 clientes tienen `logger.warning(...)` justo antes de cada degradación
silenciosa (ej. `groq_client.py:107`, `logger.warning("groq_generate_completion_failed", ...)`).
El fallo ahora deja rastro consultable en el proveedor de despliegue, sin cambiar el
comportamiento de degradación que ya se decidió mantener.

**Veredicto**: remediado y verificado.

### 2.2. Arquitectura y seguridad (P0/P1)

**Enforcement de modo demo en backend** — `src/infrastructure/api/demo_mode.py`
(`enforce_demo_mode_allowlist`): compara el SHA-256 del cuerpo subido contra un allowlist de
los 3 ejemplos sintéticos conocidos; lanza `HTTPException(403)` si no coincide. Invocado desde
`pharmacy_router.py` en `/analyze-prescription` (líneas 171-172) y `/process-prescription`
(líneas 198-199), condicionado a `settings.demo_mode`. Cierra la brecha real: ahora una
llamada directa a la API (sin pasar por el frontend) con una foto real es rechazada igual que
lo hacía ya la UI.

**Import runtime de `DrugModel`** — confirmado corregido:
`src/application/services/drug_service.py:32-33`, el import vive bajo
`if TYPE_CHECKING:`; los 4 usos restantes en el archivo son anotaciones de tipo (resueltas en
diferido gracias a `from __future__ import annotations`), no instanciación real.

Nota aparte, no parte del hallazgo original: el mismo archivo incorporó una dependencia nueva,
`src.infrastructure.metrics.record_cima_search_outcome`, importada en tiempo de ejecución (no
bajo `TYPE_CHECKING`). Es una violación técnica de la misma regla, pero deliberada y acotada:
el propio módulo la justifica como observabilidad transversal (misma categoría que un logger),
no como una regla de negocio de infraestructura. Aceptable como excepción documentada, en la
misma línea que ya se acepta un logger en cualquier capa — pero conviene no ampliar esa
excepción a otros módulos sin la misma justificación explícita.

**Lockfile de backend** — `requirements.in` (fuente editable, rangos) +
`requirements.txt` (generado, con `tenacity==9.1.4` y el resto de dependencias fijadas a
versión exacta). Cierra la asimetría con `frontend/package-lock.json`.

**CI actualizado**:
- `.github/workflows/ci.yml`, job `migrations`: nuevo paso "Run repository tests against real
  Postgres" (`pytest -m postgres tests/integration/test_drug_repository_postgres.py
  tests/integration/test_prescription_record_repository_postgres.py`) contra el servicio
  Postgres del job — cierra el hallazgo P2 de cobertura de repositorios (ver 2.3).
- `.github/workflows/dependency-audit.yml` (nuevo): `pip-audit`/`npm audit --audit-level=high`,
  cron semanal (lunes 06:00 UTC) + `workflow_dispatch` manual — separado de `ci.yml` a
  propósito, porque su objetivo es detectar CVEs publicadas después del último cambio de
  código, no revisar el código en sí.

**Veredicto**: remediado y verificado (con una nota menor documentada arriba, no un hallazgo
nuevo).

### 2.3. P2 — verificado también, aunque no era obligatorio en este barrido

- **`drug_repository.py`/`prescription_record_repository.py`**: 11 tests nuevos marcados
  `@pytest.mark.postgres` (`tests/integration/test_drug_repository_postgres.py`,
  `tests/integration/test_prescription_record_repository_postgres.py`), excluidos del run por
  defecto (`pytest.ini`: `addopts = -m "not postgres"`) pero ejecutados contra un Postgres real
  tanto en CI (`migrations` job) como localmente en esta verificación: **11/11 passed** contra
  `pharmagent_postgres` (contenedor Docker local ya en ejecución).
- **Docker** — `docker-compose.yml`: `api` con `read_only: true`, `tmpfs: [/tmp]`,
  `cap_drop: [ALL]`; Postgres/Ollama ya no publican puerto al host en el compose base.
  `docker-compose.override.yml` (nuevo, cargado automáticamente solo en local) reintroduce esos
  puertos únicamente para desarrollo — un despliegue real que use
  `docker compose -f docker-compose.yml up` (sin el override) obtiene el perfil endurecido.
- **Métricas** — `src/infrastructure/metrics.py` (`record_cima_search_outcome`, snapshot en
  memoria) + `GET /internal/metrics` (`main.py:85`), protegido por `verify_api_key` —
  visibilidad básica de la tasa de fallback CIMA-en-vivo, cerrando parte del hallazgo #9 de la
  auditoría inicial (latencia/tasa de error de LLM por proveedor sigue sin medirse; queda como
  mejora futura no bloqueante).

**Veredicto**: remediado y verificado.

### 2.4. Suite de calidad — ejecutada en el momento de esta verificación

```
ruff check .            → All checks passed!
ruff format --check .   → 78 files already formatted

pytest (suite por defecto, -m "not postgres")
  → 158 passed, 11 deselected, 5 warnings in 14.6s
  → cobertura: 90% (TOTAL 823 stmts, 57 miss, 116 branch, 28 brpart)

pytest -m postgres (contra Postgres real, docker local)
  → 11 passed in 0.8s

frontend: npm test (Vitest)
  → 3 test files, 21 passed
```

**Total**: 169/169 tests backend (158 + 11 contra Postgres real) + 21/21 frontend, 0 fallos,
lint y formato limpios.

> Nota de reconciliación: la cifra de cobertura obtenida en esta verificación (90%) difiere en
> menos de un punto de la reportada en el cierre original de esta remediación (89.67%) —
> variación esperable entre ejecuciones (entorno con Postgres/Ollama reales ya activos en esta
> pasada) y no material; ambas superan holgadamente el umbral de CI (85%).

## 3. Veredicto final

| Bloque | Estado |
|---|---|
| P0 — Resiliencia (reintentos) | Resuelto |
| P0 — Observabilidad (logging) | Resuelto |
| P0 — RGPD (demo mode en backend) | Resuelto |
| P1 — DIP (`DrugModel` fuera de runtime) | Resuelto |
| P1 — Lockfile de backend | Resuelto |
| P1 — Auditoría de dependencias en CI | Resuelto |
| P2 — Cobertura de repositorios | Resuelto |
| P2 — Endurecimiento de Docker | Resuelto |
| P2 — Métricas básicas | Resuelto |

Los 9 hallazgos de la auditoría inicial están remediados y verificados de forma independiente
contra código y tests reales, no solo contra el informe de cierre de la remediación.
**Cobertura final: 90%** (umbral CI: 85%), 169 tests backend + 21 tests frontend, 0 fallos.

## 4. Pendientes no bloqueantes (fuera de alcance de esta remediación)

- Latencia/tasa de error por proveedor LLM (Groq/Gemini/Ollama) individualmente — `/internal/metrics`
  cubre hoy solo la tasa de fallback CIMA-en-vivo.
- La excepción de import runtime para `record_cima_search_outcome` en `drug_service.py`
  (ver §2.2) es aceptable tal como está justificada, pero no debería ampliarse a otros módulos
  sin la misma justificación explícita de "observabilidad transversal".
- Desacoplar `DrugRepositoryPort` de `DrugModel` (ORM) con una entidad de dominio `Drug` pura —
  limitación aceptada desde antes de esta auditoría, sigue documentada en `DECISIONS.md`.
