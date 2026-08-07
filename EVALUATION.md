# EVALUATION.md — Evaluación cuantitativa de PharmAgent

Evaluación empírica de `SafetyCheckAgent` y `PrescriptionAgent` sobre un dataset sintético,
ejecutada contra los servicios reales del proyecto (Ollama local `llama3`, Google Gemini).
Complementa la verificación funcional (tests, `TestClient`) con métricas de exactitud y
latencia — algo que el proyecto no tenía hasta este bloque de trabajo.

## Metodología

- **Dataset**: [evaluation/dataset.py](evaluation/dataset.py) — 7 casos de interacciones
  farmacológicas y 3 recetas sintéticas. Todos los casos son **inventados para esta
  evaluación**, no proceden de pacientes ni recetas reales.
- **`SafetyCheckAgent`**: 3 casos cubiertos por la base curada interna (`_KNOWN_INTERACTIONS`
  en [safety_agent.py](src/application/agents/safety_agent.py)) y 4 casos deliberadamente
  fuera de esa base, para ejercitar el camino de razonamiento vía `llama3` local. El
  veredicto de referencia (`expected_verdict`) de los 4 casos LLM se basa en conocimiento
  farmacológico público y establecido (p. ej. la contraindicación IMAO+ISRS), no en la base
  curada del propio agente — evita una evaluación circular.
- **`PrescriptionAgent`**: 3 imágenes de receta generadas sintéticamente con Pillow
  ([evaluation/generate_synthetic_prescriptions.py](evaluation/generate_synthetic_prescriptions.py)),
  texto renderizado sobre fondo blanco — no son fotografías ni escaneos reales. Se mide
  *recall*: proporción de nombres de fármaco esperados que aparecen (subcadena,
  insensible a mayúsculas) en la extracción del agente.
- **Reproducción**: `python -m evaluation.run_evaluation` (requiere Ollama local con
  `llama3` descargado; la parte de `PrescriptionAgent` se omite automáticamente si
  `GOOGLE_API_KEY` no está configurada). Resultados crudos en
  [evaluation/results.json](evaluation/results.json) (regenerado en cada ejecución).

**Por qué no es un gate de CI**: el LLM (tanto `llama3` como Gemini) no es determinista
entre ejecuciones, y la evaluación completa tarda 1-2 minutos (latencia real de inferencia)
— no es apropiado como parte del pipeline de lint/test rápido de
[.github/workflows/ci.yml](.github/workflows/ci.yml). Se documenta como snapshot manual,
re-ejecutable bajo demanda.

## Resultados (ejecución de referencia: 2026-08-05)

### `SafetyCheckAgent` — 7/7 veredictos correctos

| Caso | Fármacos | Esperado | Obtenido | Fuente | Latencia |
|---|---|---|---|---|---|
| `curated-warfarina-aspirina` | Warfarina + Aspirina | `requiere_revision_medica` | igual | `curated` | 0.0s |
| `curated-ibuprofeno-aspirina` | Ibuprofeno + Aspirina | `apto_con_precaucion` | igual | `curated` | 0.0s |
| `curated-fluoxetina-tramadol` | Fluoxetina + Tramadol | `requiere_revision_medica` | igual | `curated` | 0.0s |
| `llm-imao-isrs` | Fenelzina + Sertralina | `requiere_revision_medica` | igual | `llm` | 16.5s |
| `llm-digoxina-amiodarona` | Digoxina + Amiodarona | `requiere_revision_medica` | igual | `llm` | 18.6s |
| `llm-metformina-furosemida` | Metformina + Furosemida | `apto_con_precaucion` | igual | `llm` | 19.5s |
| `llm-paracetamol-amoxicilina-no-interaction` | Paracetamol + Amoxicilina | `apto` | igual | — | 3.4s |

Los 3 casos cubiertos por la base curada responden en ~0s (sin llamada a Ollama, tal como
diseñado — ver "Diseño híbrido" en `safety_agent.py`). Los 4 casos que requieren
razonamiento del LLM tardan 3-20s, coherente con la latencia real de `llama3` en CPU sin GPU,
incluyendo el arranque en frío conocido de Ollama.

### `PrescriptionAgent` — recall medio = 1.0 (3/3 casos, extracción perfecta)

| Caso | Esperado | Extraído | Recall | Latencia |
|---|---|---|---|---|
| `rx-single-drug` | `[ibuprofeno]` | `[ibuprofeno]` | 1.0 | 6.4s |
| `rx-two-drugs` | `[amoxicilina, paracetamol]` | `[amoxicilina, paracetamol]` | 1.0 | 3.7s |
| `rx-three-drugs` | `[omeprazol, warfarina, aspirina]` | `[omeprazol, warfarina, aspirina]` | 1.0 | 4.1s |

Nota de alcance: las imágenes son texto sintético limpio, no recetas manuscritas ni
fotografiadas con ruido real — el recall=1.0 mide correctamente la capacidad de extracción
estructurada del modelo sobre texto legible, pero **no** es evidencia de robustez ante OCR
de escritura manuscrita real o imágenes de baja calidad (fuera de alcance de este dataset).

## Hallazgos durante la evaluación (no solo resultados — también bugs reales encontrados)

1. **`gemini-1.5-pro` retirado por Google** (descubierto al depurar un recall=0.0 en la
   primera ejecución): el modelo usado por `GeminiClient` desde su implementación original
   (BLOQUE B) devolvía `404 NOT_FOUND` para esta `GOOGLE_API_KEY` — Google lo ha retirado
   para claves nuevas. **Corregido**: `GeminiClient.DEFAULT_MODEL` ahora usa
   `gemini-flash-latest` (alias siempre apuntando al modelo Flash estable más reciente),
   verificado multimodal contra las 3 imágenes sintéticas con recall=1.0 tras el cambio.
   `gemini-2.5-pro`/`gemini-2.0-flash` también existen pero devolvieron
   `429 RESOURCE_EXHAUSTED` con la cuota gratuita de esta API key. Este hallazgo es
   independiente del propio dataset de evaluación — es un bug de producción real que
   afectaba a `/analyze-prescription` y `/process-prescription` antes de esta corrección.
2. **Falso positivo en la primera ejecución de `llm-imao-isrs`**: antes de investigar,
   ese caso devolvió `correct: true` pero `actual_sources: []` con una latencia de
   exactamente 60.029s — coincide con `OllamaClient.DEFAULT_TIMEOUT_SECONDS = 60.0`. La
   llamada a `llama3` agotó el timeout, `SafetyCheckAgent._parse_llm_response` no recibió
   respuesta interpretable, y el veredicto por defecto ante fallo de parseo
   (`requiere_revision_medica`) **coincidió por casualidad** con el veredicto esperado — no
   fue razonamiento real del modelo. Se documenta aquí explícitamente para no presentar un
   "acierto" que en realidad fue una degradación defensiva; la ejecución de referencia de
   este documento es una re-ejecución posterior sin timeout, donde el caso sí completó con
   `source: "llm"`. Esto confirma que el diseño "ante incertidumbre, nunca aprobar
   silenciosamente" (ver AGENTS.md) funciona correctamente incluso cuando el LLM no responde
   a tiempo — pero también expone que un timeout no se distingue de una respuesta genuina en
   la salida actual (`actual_sources: []` en ambos casos de "no interacciones" y de fallo de
   parseo). Ver "Limitaciones" más abajo.

## Limitaciones de esta evaluación

- **Tamaño del dataset**: 7 + 3 = 10 casos totales. Suficiente para detectar regresiones
  groseras y validar el diseño híbrido curada+LLM, insuficiente para una estimación
  estadísticamente robusta de precisión/recall en producción.
- **Sin distinción entre "sin interacción" y "fallo silencioso"**: como se documenta en el
  hallazgo 2, `SafetyCheckAgent` no expone hoy si `interactions: []` proviene de una
  respuesta genuina del LLM ("no encontré nada") o de un fallo de parseo/timeout que cayó en
  el mismo valor por defecto en el caso `apto`. Distinguir ambos casos explícitamente (p. ej.
  un campo `llm_response_status`) queda como mejora futura.
- **Recetas sintéticas, no reales**: como se indica arriba, el recall=1.0 de
  `PrescriptionAgent` no debe interpretarse como una tasa de éxito esperada sobre recetas
  manuscritas o fotografiadas en condiciones reales.
- **No determinista**: al depender de LLMs reales, una re-ejecución puede dar resultados
  ligeramente distintos (especialmente en los 4 casos de razonamiento libre de
  `SafetyCheckAgent`). El snapshot de este documento corresponde a una ejecución concreta,
  fechada, no a una garantía permanente.
