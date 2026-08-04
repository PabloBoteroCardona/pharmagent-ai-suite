# PharmAgent AI Suite

Trabajo de Fin de Máster (TFM) — sistema multiagente para el procesamiento de recetas
médicas, la verificación de interacciones farmacológicas y la consulta en lenguaje natural
de fichas técnicas oficiales de medicamentos autorizados en España (AEMPS/CIMA).

## Índice

- [Descripción y objetivos](#descripción-y-objetivos)
- [Stack tecnológico y arquitectura](#stack-tecnológico-y-arquitectura)
- [Requisitos previos](#requisitos-previos)
- [Instrucciones de despliegue en local](#instrucciones-de-despliegue-en-local)
- [Endpoints de la API](#endpoints-de-la-api)
- [Pruebas automatizadas](#pruebas-automatizadas)
- [Estado del proyecto](#estado-del-proyecto)

## Descripción y objetivos

PharmAgent AI Suite explora hasta qué punto un sistema multiagente, construido con
disciplina de Clean Architecture, puede apoyar tres tareas farmacéuticas concretas sin
comprometer la seguridad del paciente ni la privacidad de los datos de salud que maneja:

1. **Extracción estructurada de recetas** a partir de una imagen (foto o escaneo), usando
   comprensión multimodal (`PrescriptionAgent`, Gemini 1.5 Pro).
2. **Verificación de interacciones farmacológicas** conocidas entre los fármacos de una
   receta (`SafetyCheckAgent`), con un veredicto explícito y nunca una aprobación silenciosa
   ante una interacción grave.
3. **Consulta en lenguaje natural** sobre fichas técnicas oficiales de medicamentos
   (`RAGPharmAgent`), con respuestas *grounded* — basadas únicamente en la información
   recuperada, nunca en conocimiento no verificado del modelo.

Un principio de diseño transversal, motivado por tratarse de datos de salud (categoría
especial según RGPD/LOPDGDD): **los embeddings y la generación de texto para RAG se ejecutan
siempre en local vía Ollama**; la única llamada a un proveedor externo (Google Gemini) es la
comprensión multimodal de imágenes de recetas, que no tiene alternativa local viable con
calidad suficiente. Ver el detalle de esta y otras decisiones de arquitectura en
[.memory/DECISIONS.md](.memory/DECISIONS.md).

## Stack tecnológico y arquitectura

| Capa | Tecnología |
|---|---|
| API web | FastAPI (async), Uvicorn |
| Validación / esquemas | Pydantic v2 |
| Persistencia | PostgreSQL 16 + `pgvector` (caché semántica), SQLAlchemy 2.0 async, `asyncpg` |
| LLM local | Ollama (`llama3` para generación, `nomic-embed-text` para embeddings) |
| LLM multimodal remoto | Google Gemini 1.5 Pro (`google-genai`), exclusivo para extracción de recetas |
| Fuente de datos oficial | API REST de CIMA/AEMPS (`https://cima.aemps.es/cima/rest`) |
| Observabilidad | Sentry (`sentry-sdk`, captura de errores a nivel de aplicación) |
| Configuración | `pydantic-settings` (fuente única de variables de entorno) |
| Calidad | Ruff (lint + format), Pytest, GitHub Actions |

### Arquitectura: Clean Architecture / monolito modular

Se adopta un monolito modular en capas concéntricas — ver
[ADR 001](docs/adr/001-stack-python-adk.md) para la justificación completa — con una regla
de dependencia estricta: **`src/domain/` no importa nada fuera de la librería estándar de
Python y Pydantic**. Las capas externas dependen del dominio a través de interfaces
(`typing.Protocol`), nunca al revés.

```
src/
├── domain/                  # Núcleo: reglas de negocio puras, sin dependencias externas
│   ├── models/                # Entidades: Prescription, PrescribedDrug, DrugInteraction
│   └── ports/                  # Interfaces (Protocol) que la infraestructura satisface
├── application/              # Casos de uso y agentes, dependen solo de domain/ports/
│   ├── agents/                 # RAGPharmAgent, PrescriptionAgent, SafetyCheckAgent
│   └── services/                # DrugService (orquestación CIMA + Ollama + pgvector)
├── use_cases/                # Puntos de entrada explícitos e independientes del transporte
└── infrastructure/           # Framework web, clientes externos, persistencia, configuración
    ├── api/                     # FastAPI: routers, esquemas Pydantic REST, main.py
    ├── config/                   # pydantic-settings (única fuente de variables de entorno)
    ├── external/                  # CimaAPIClient, OllamaClient, GeminiClient
    ├── models/ · repositories/     # ORM SQLAlchemy + pgvector, repositorios
    └── database.py                # Motor async de PostgreSQL
```

La inversión de dependencias se aplica mediante tipado estructural: `DrugService` y los
agentes de `application/` dependen de puertos (`CimaDataSourcePort`, `LanguageModelPort`,
`DrugRepositoryPort`, `PrescriptionVisionPort` en
[drug_ports.py](src/domain/ports/drug_ports.py)), no de las clases concretas de
`infrastructure/`. Estas últimas los satisfacen por estructura (`Protocol`
`@runtime_checkable`), sin herencia — verificable con `isinstance()`. Esto permite sustituir
cualquier proveedor externo (o testear con dobles en memoria, ver
[Pruebas automatizadas](#pruebas-automatizadas)) sin tocar el dominio ni los agentes.

> Los agentes se documentan en detalle en [AGENTS.md](AGENTS.md) y las herramientas
> (*tools*) que definen su contrato conceptual en [SKILLS.md](SKILLS.md). Ambos documentos
> distinguen explícitamente el diseño objetivo original (orquestación vía Google ADK) del
> estado real implementado (invocación directa de métodos Python asíncronos).

## Requisitos previos

- **Python 3.11+** (desarrollado y probado con 3.14).
- **Docker** y **Docker Compose** (para PostgreSQL + pgvector y Ollama).
- Una **API key de Google Gemini** (opcional — solo necesaria para probar
  `/analyze-prescription`; el resto de la API funciona sin ella). Se obtiene en
  [Google AI Studio](https://aistudio.google.com/).

## Instrucciones de despliegue en local

1. **Clonar el repositorio e instalar dependencias** en un entorno virtual:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   # source .venv/bin/activate     # Linux/macOS
   pip install -r requirements.txt
   ```

2. **Levantar PostgreSQL (pgvector) y Ollama** con Docker Compose:

   ```bash
   docker-compose up -d
   ```

3. **Descargar los modelos de Ollama** (una sola vez; persisten en el volumen
   `ollama_data`):

   ```bash
   docker exec pharmagent_ollama ollama pull nomic-embed-text
   docker exec pharmagent_ollama ollama pull llama3
   ```

4. **Configurar las variables de entorno**: copiar `.env.example` a `.env` y ajustar lo
   necesario (por defecto ya apunta al PostgreSQL/Ollama de `docker-compose.yml`):

   ```bash
   cp .env.example .env
   ```

   Añadir `GOOGLE_API_KEY` en `.env` solo si se va a probar `/analyze-prescription`.
   `EMBEDDING_PROVIDER` debe permanecer en `ollama` — ver
   [.memory/DECISIONS.md](.memory/DECISIONS.md) sobre por qué los embeddings nunca usan un
   proveedor externo.

5. **Inicializar el esquema de base de datos** (habilita la extensión `pgvector` y crea las
   tablas):

   ```bash
   python -m src.infrastructure.init_db
   ```

6. **(Opcional) Poblar la caché semántica** con una ingesta inicial desde CIMA en vivo:

   ```bash
   python -m scripts.ingest_drugs
   ```

7. **Arrancar la API**:

   ```bash
   uvicorn src.infrastructure.api.main:app --reload --port 8000
   ```

   La documentación interactiva (OpenAPI/Swagger) queda disponible en
   `http://localhost:8000/docs`.

## Endpoints de la API

Prefijo común: `/api/v1/pharmacy` (excepto `/health`).

| Método | Ruta | Descripción | Agente / servicio |
|---|---|---|---|
| `GET` | `/health` | Comprobación de disponibilidad del servicio | — |
| `POST` | `/search` | Búsqueda semántica de fármacos en la caché vectorial | `DrugService` |
| `POST` | `/consult` | Consulta en lenguaje natural, respuesta *grounded* | `RAGPharmAgent` |
| `POST` | `/check-interactions` | Verificación de interacciones entre 2+ fármacos | `SafetyCheckAgent` |
| `POST` | `/analyze-prescription` | Extracción estructurada desde imagen de receta | `PrescriptionAgent` |

### Ejemplos de uso

**Búsqueda semántica** (`POST /api/v1/pharmacy/search`):

```json
// Request
{ "query": "antiinflamatorio para dolor de cabeza", "limit": 3 }
```

```json
// Response 200
[
  {
    "nregistro": "80298",
    "nombre": "Ibuprofeno Test 600mg",
    "pactivos": "ibuprofeno",
    "labtitular": "Laboratorio Test S.A."
  }
]
```

**Consulta RAG** (`POST /api/v1/pharmacy/consult`):

```json
// Request
{ "query": "¿qué dosis de ibuprofeno es adecuada para un adulto?" }
```

```json
// Response 200
{
  "query": "¿qué dosis de ibuprofeno es adecuada para un adulto?",
  "response": "La dosis habitual en adultos es de 400-600 mg cada 8 horas...",
  "sources": ["Ibuprofeno Test 600mg"]
}
```

**Verificación de interacciones** (`POST /api/v1/pharmacy/check-interactions`):

```json
// Request
{ "drugs": ["Warfarina 5mg", "Aspirina 100mg"] }
```

```json
// Response 200
{
  "interactions": [
    {
      "primary_drug": "warfarina",
      "secondary_drug": "aspirina",
      "severity": "SEVERE",
      "description": "Efecto anticoagulante/antiagregante combinado: aumenta significativamente el riesgo de hemorragia.",
      "clinical_recommendation": "Evitar la combinación salvo indicación médica expresa; si es necesaria, monitorizar INR estrechamente."
    }
  ],
  "verdict": "requiere_revision_medica"
}
```

**Análisis de receta** (`POST /api/v1/pharmacy/analyze-prescription`, `multipart/form-data`
con campo `file`):

```json
// Response 200
{
  "drugs": [
    { "farmaco": "Ibuprofeno", "dosificacion": "600 mg", "frecuencia": "cada 8 horas", "duracion": "5 días" }
  ],
  "advertencias": ["Tomar con alimentos."]
}
```

## Pruebas automatizadas

```bash
pytest              # suite completa (unit + integration)
ruff check .         # lint
ruff format --check .  # formato
```

La suite (`tests/unit/`, `tests/integration/`) es determinista y no requiere Docker, red ni
credenciales: las dependencias externas (CIMA, Ollama, PostgreSQL, Gemini) se sustituyen por
dobles en memoria vía `app.dependency_overrides` de FastAPI (ver
[tests/integration/conftest.py](tests/integration/conftest.py)), aprovechando que la propia
arquitectura de puertos del dominio hace estos dobles triviales de construir. El pipeline de
integración continua ([.github/workflows/ci.yml](.github/workflows/ci.yml)) ejecuta lint,
formato y tests en cada `push`/`pull_request` a `main`.

## Estado del proyecto

Progreso detallado, decisiones de arquitectura y bugs resueltos se documentan de forma viva
en [.memory/](.memory/) (`CONTEXT.md`, `ROADMAP.md`, `DECISIONS.md`, `BUGS.md`) siguiendo el
protocolo de memoria descrito en [CLAUDE.md](CLAUDE.md). En resumen: los tres agentes, la
API REST completa, la ingesta desde CIMA, la suite de tests y el pipeline de CI están
implementados y verificados contra servicios reales. Limitaciones conocidas y aceptadas
(fuera de alcance hasta ahora): la base de interacciones de `SafetyCheckAgent` es curada y
mínima (no una fuente clínica completa), `RAGPharmAgent` consulta solo la caché vectorial
local por petición (CIMA en vivo se usa únicamente en la ingesta por lotes), y no existe
todavía una entidad de dominio `Drug` desacoplada del modelo ORM.
