# AGENTS.md — PharmAgent AI Suite

Especificación de los agentes construidos sobre el **Google Agent Development Kit (ADK)**.
Cada agente vive tras un puerto de dominio (`src/domain/services`) y se implementa como
adaptador concreto en `src/adapters/adk/`, siguiendo Clean Architecture: el dominio no conoce
detalles de ADK, modelos o proveedores — solo interfaces.

Las herramientas (`tools`) que invocan estos agentes están definidas con esquemas Pydantic v2
en [SKILLS.md](SKILLS.md).

---

## 1. PrescriptionAgent

**Propósito**: extraer datos estructurados de recetas médicas a partir de imágenes (foto,
escaneo o PDF) mediante comprensión multimodal.

| Campo | Valor |
|---|---|
| **Modelo** | `gemini-1.5-pro` (multimodal, vía Google GenAI SDK) |
| **Tipo ADK** | `LlmAgent` con `Content` multimodal (imagen + texto) |
| **Ubicación** | `src/adapters/adk/prescription_agent.py` |
| **Puerto de dominio** | `src/domain/services/prescription_extraction_service.py` (interfaz) |
| **Herramienta principal** | `extract_prescription_from_image` (ver SKILLS.md) |
| **Modo de ejecución** | Remoto (API de Google), latencia tolerable para flujo síncrono de subida de receta |

### Responsabilidades
- Recibir la imagen de la receta (bytes o URI) y el contexto del paciente (opcional).
- Aplicar OCR + comprensión de layout para identificar: médico prescriptor, colegiado,
  paciente, fármacos, dosis, posología, duración del tratamiento y fecha.
- Normalizar nombres de fármacos contra el vocabulario de principios activos (para
  facilitar el cruce posterior con `SafetyCheckAgent`).
- Devolver una respuesta **estructurada y validada** (Pydantic) — nunca texto libre — junto
  con un `confidence_score` por campo para permitir revisión humana en casos dudosos.
- Señalar campos ilegibles o ambiguos como `null` en lugar de inventar datos (mitigación de
  alucinaciones en un dominio crítico para la seguridad del paciente).

### Instrucciones del sistema (resumen)
> Eres un asistente farmacéutico que transcribe recetas médicas con precisión clínica.
> Nunca inventes dosis, fármacos o datos del paciente que no sean legibles en la imagen.
> Si un campo no es legible con certeza, devuélvelo como `null` y baja su `confidence_score`.
> Responde exclusivamente invocando la herramienta `extract_prescription_from_image`.

### Entradas / salidas
- **Entrada**: imagen (`image/jpeg`, `image/png` o `application/pdf`), `patient_id` opcional.
- **Salida**: `PrescriptionExtractionResult` (ver SKILLS.md) consumido por el caso de uso
  `src/use_cases/process_prescription.py`.

### Consideraciones de seguridad y cumplimiento
- Las imágenes de recetas contienen datos de salud (categoría especial, RGPD/LOPDGDD).
  No se persisten en logs ni se envían a servicios de telemetría (ver
  `src/infrastructure/observability`).
- Toda extracción con `confidence_score` por debajo del umbral configurado
  (`PRESCRIPTION_MIN_CONFIDENCE`, `.env`) debe enrutarse a revisión manual antes de continuar
  el flujo hacia `SafetyCheckAgent`.

---

## 2. SafetyCheckAgent

**Propósito**: detectar interacciones medicamentosas, contraindicaciones y alertas de
seguridad a partir de la lista de fármacos ya extraída.

| Campo | Valor |
|---|---|
| **Modelo** | `llama-3.1` (despliegue local, p. ej. vía Ollama/vLLM) con *fallback* a `gemini-1.5-pro` |
| **Tipo ADK** | `LlmAgent` con `tool_choice` forzado a `check_drug_interactions` |
| **Ubicación** | `src/adapters/adk/safety_check_agent.py` |
| **Puerto de dominio** | `src/domain/services/drug_safety_service.py` (interfaz) |
| **Herramienta principal** | `check_drug_interactions` (ver SKILLS.md) |
| **Modo de ejecución** | Preferentemente local (datos clínicos sensibles, baja latencia, sin
  dependencia de red externa); Gemini solo como *fallback* si el modelo local no está
  disponible, nunca como ruta por defecto para reducir exposición de datos de salud |

### Responsabilidades
- Recibir la lista normalizada de principios activos (salida de `PrescriptionAgent`) más,
  opcionalmente, la medicación crónica del paciente.
- Consultar la base de interacciones (vía la herramienta `check_drug_interactions`, que
  encapsula el acceso a la fuente de datos — AEMPS/CIMA u otra base curada).
- Clasificar cada interacción encontrada por severidad (`leve`, `moderada`, `grave`,
  `contraindicada`) y explicar el mecanismo farmacológico de forma comprensible.
- Emitir una recomendación explícita: `apto`, `apto_con_precaucion` o `requiere_revision_medica`.
- **Nunca** aprobar silenciosamente una combinación — ante ambigüedad o datos insuficientes,
  el veredicto por defecto es `requiere_revision_medica`.

### Instrucciones del sistema (resumen)
> Eres un sistema de verificación de seguridad farmacológica. Tu prioridad absoluta es la
> seguridad del paciente sobre la conveniencia. Ante cualquier duda o falta de evidencia
> suficiente, clasifica el caso como `requiere_revision_medica`. Nunca minimices una
> interacción grave. Justifica siempre tu veredicto citando la interacción concreta detectada
> por la herramienta `check_drug_interactions`; no generes interacciones que la herramienta
> no haya devuelto.

### Entradas / salidas
- **Entrada**: `List[NormalizedDrug]` + `patient_context` opcional (edad, alergias,
  medicación crónica, embarazo/lactancia si aplica).
- **Salida**: `DrugInteractionReport` (ver SKILLS.md) consumido por
  `src/use_cases/validate_prescription_safety.py`.

### Consideraciones de seguridad y cumplimiento
- Al ejecutarse localmente por defecto, minimiza la salida de datos clínicos hacia terceros.
- Todo veredicto y su justificación se persisten de forma auditable (trazabilidad clínica),
  sin almacenar el prompt completo si contiene PII más allá de lo necesario.

---

## 3. RAGPharmAgent

**Propósito**: responder preguntas en lenguaje natural sobre fichas técnicas de
medicamentos (AEMPS/CIMA) mediante *Retrieval-Augmented Generation*.

| Campo | Valor |
|---|---|
| **Modelo** | `gemma-2` (despliegue local) |
| **Tipo ADK** | `LlmAgent` con herramienta de recuperación (`search_cima_vector_db`) precediendo a la generación |
| **Ubicación** | `src/adapters/adk/rag_pharm_agent.py` |
| **Puerto de dominio** | `src/domain/services/pharma_knowledge_service.py` (interfaz) |
| **Herramienta principal** | `search_cima_vector_db` (ver SKILLS.md) |
| **Almacén vectorial** | PostgreSQL + `pgvector` (`src/adapters/rag/`), poblado offline a partir de las fichas técnicas públicas de AEMPS/CIMA |
| **Modo de ejecución** | Local (consultas frecuentes, coste marginal bajo, sin necesidad de capacidad multimodal) |

### Responsabilidades
- Recibir la pregunta del usuario (profesional sanitario o paciente) sobre un medicamento.
- Invocar `search_cima_vector_db` para recuperar los fragmentos más relevantes de la ficha
  técnica (posología, contraindicaciones, efectos adversos, excipientes, condiciones de
  conservación, etc.).
- Generar una respuesta **basada exclusivamente en los fragmentos recuperados**, citando el
  medicamento y la sección de la ficha técnica de origen.
- Si la base vectorial no devuelve resultados con similitud suficiente, responder que no
  dispone de información verificada en lugar de generar una respuesta no fundamentada.

### Instrucciones del sistema (resumen)
> Eres un asistente de consulta de fichas técnicas de medicamentos autorizados en España
> (AEMPS/CIMA). Responde únicamente con información contenida en los fragmentos recuperados
> por `search_cima_vector_db`. Si los fragmentos no contienen la respuesta, indica
> explícitamente que no hay información verificada disponible; no completes con
> conocimiento general no verificado. Cita siempre el nombre del medicamento y la sección de
> la ficha técnica utilizada.

### Entradas / salidas
- **Entrada**: `query: str`, `drug_name` opcional para acotar la búsqueda.
- **Salida**: `RAGAnswer` (ver SKILLS.md), con `answer`, `sources` (lista de fragmentos y
  metadatos) y `grounded: bool` indicando si la respuesta está respaldada por recuperación.
- Consumido por `src/use_cases/answer_pharma_query.py`.

### Consideraciones de seguridad y cumplimiento
- No sustituye el prospecto oficial ni el criterio de un profesional sanitario; toda
  respuesta debe incluir el aviso correspondiente (gestionado en la capa de presentación,
  `src/infrastructure/api/routers`).
- La base vectorial se actualiza mediante un proceso ETL versionado y auditable; el agente
  nunca escribe en el índice, solo lo consulta (principio de menor privilegio).

---

## Convenciones comunes a los tres agentes

- **Orquestación**: los tres agentes se registran como *tools* de un agente orquestador de
  nivel superior (o se invocan secuencialmente desde los casos de uso), nunca se acoplan
  entre sí directamente — la composición vive en `src/use_cases/`.
- **Contratos**: toda entrada/salida entre el dominio y un agente ADK pasa por los esquemas
  Pydantic v2 definidos en [SKILLS.md](SKILLS.md); ningún agente devuelve texto libre sin
  validar al dominio.
- **Observabilidad**: cada invocación se traza con Sentry (`src/infrastructure/observability`)
  registrando latencia, modelo usado y resultado (éxito/fallback/error), sin registrar PII de
  salud en claro.
- **Configuración**: nombres de modelo, endpoints locales y umbrales de confianza se leen de
  variables de entorno (`.env`, ver `.env.example`) a través de
  `src/infrastructure/config`, nunca hardcodeados en el adaptador.
