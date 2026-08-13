# ADR 001 — Stack tecnológico: Python 3.11+, Monolito Modular con Clean Architecture, FastAPI, Google ADK y PostgreSQL + pgvector

## Estado

Aceptado — 2026-08-04.

> **Nota de estado real (añadida posteriormente, no reescribe la decisión original):**
> la sección 4 (Google ADK) describe el diseño conceptual objetivo en el momento de
> esta decisión, pero no se adoptó en la implementación final — los tres agentes
> (`PrescriptionAgent`, `SafetyCheckAgent`, `RAGPharmAgent`) son clases Python `async`
> simples que dependen de puertos de dominio (`src/domain/ports/`), sin el SDK de
> Google ADK ni la carpeta `src/adapters/adk/` descrita más abajo. El resto de la
> decisión (Python, Clean Architecture, FastAPI, PostgreSQL + pgvector) sí se mantiene
> tal cual. Ver la nota "Estado real" en [AGENTES.md](../AGENTES.md) para el detalle
> agente por agente.

## Contexto

PharmAgent es un Trabajo de Fin de Máster (TFM) que implementa un sistema
multiagente para el procesamiento de recetas médicas, verificación de interacciones
farmacológicas y consulta de fichas técnicas (AEMPS/CIMA). El sistema maneja datos de
salud (categoría especial según RGPD/LOPDGDD), debe ser evaluable en un entorno
académico con recursos limitados, y necesita combinar modelos de lenguaje remotos
(multimodales) y locales dentro del mismo flujo. Se requiere una arquitectura que:

- Sea comprensible y defendible en el contexto de un TFM (alcance acotado, sin
  sobreingeniería de microservicios).
- Aísle el dominio (reglas de negocio farmacéutico-clínicas) de los detalles de
  infraestructura, proveedores de modelos y framework web, para que estos últimos
  puedan cambiar sin afectar la lógica clínica.
- Soporte búsqueda semántica sobre fichas técnicas (RAG) sin depender de un servicio
  vectorial externo adicional.
- Permita testear el dominio sin necesidad de levantar base de datos, red o modelos.

## Decisión

Se adopta el siguiente stack y estilo arquitectónico:

### 1. Python 3.11+

- Sintaxis moderna estable (`X | Y` en anotaciones, `tomllib`, mejoras de rendimiento
  del intérprete) con soporte amplio en el ecosistema de librerías de IA/ML a la fecha
  de inicio del proyecto.
- Compatibilidad garantizada con FastAPI, Pydantic v2, SQLAlchemy 2.0 async y el SDK
  de Google GenAI.
- Se fija `3.11+` (no una versión exacta) para no acoplar el proyecto a un único
  parche, dejando margen a los entornos de desarrollo/evaluación del TFM mientras se
  mantenga la compatibilidad de dependencias.

### 2. Monolito Modular con Clean Architecture

Se descarta una arquitectura de microservicios por sobrecoste operativo injustificado
para el alcance de un TFM (no hay necesidad real de escalado independiente por
componente ni de despliegue multi-equipo). Se adopta en su lugar un **monolito
modular** organizado en capas concéntricas (Clean Architecture / Ports & Adapters):

```
src/
├── domain/          # Entidades y reglas de negocio puras (Pydantic + stdlib únicamente)
│   ├── models/       # Prescription, DrugInteraction, etc.
│   └── services/      # Interfaces (puertos) que los adaptadores implementan
├── use_cases/        # Orquestación de casos de uso, dependen solo de domain/
├── adapters/         # Implementaciones concretas de los puertos del dominio
│   ├── adk/            # Agentes Google ADK (Prescription, SafetyCheck, RAGPharm)
│   ├── db/             # Repositorios SQLAlchemy/asyncpg
│   └── rag/             # Acceso al almacén vectorial pgvector
└── infrastructure/   # Framework web, configuración, observabilidad
    ├── api/routers/
    ├── config/
    └── observability/
```

Regla de dependencia estricta: **`domain/` no importa nada fuera de la librería
estándar de Python y Pydantic** — ni SQLAlchemy, ni FastAPI, ni el SDK de Google ADK.
Las capas externas dependen del dominio, nunca al revés. Esto permite:

- Testear entidades y reglas clínicas (p. ej. severidad de interacciones) sin
  infraestructura.
- Sustituir el proveedor de modelo (Gemini ↔ Llama local ↔ Gemma local) o el motor de
  persistencia sin tocar el dominio.
- Mantener la complejidad acorde al alcance del TFM, evitando la fragmentación en
  servicios que un monolito modular ya resuelve mediante límites de módulo.

### 3. FastAPI

- Framework web asíncrono nativo, imprescindible para no bloquear el hilo de eventos
  mientras se esperan respuestas de agentes ADK (remotos o locales) y consultas a
  PostgreSQL vía `asyncpg`.
- Integración directa con Pydantic v2 para validación de entrada/salida en la capa de
  presentación (`src/infrastructure/api`), reutilizando los mismos principios de
  tipado estricto que ya se aplican en el dominio y en los esquemas de las tools
  (ver [HERRAMIENTAS.md](../HERRAMIENTAS.md)).
- Generación automática de documentación OpenAPI, útil para la defensa y demostración
  del TFM.

### 4. Google Agent Development Kit (ADK)

- Framework de orquestación de agentes que permite definir `LlmAgent`s con `tools`
  tipadas (Pydantic) y alternar entre modelos remotos (Gemini, multimodal) y locales
  (Llama 3.1, Gemma 2) sin reescribir la lógica de orquestación — ver
  [AGENTES.md](../AGENTES.md) para el detalle de los tres agentes.
- Encaja de forma natural con la separación de puertos/adaptadores: cada agente ADK es
  un adaptador (`src/adapters/adk/`) que implementa una interfaz de dominio
  (`src/domain/services/`), de modo que el resto del sistema depende de la interfaz y
  no del SDK concreto.

### 5. PostgreSQL + pgvector

- Un único motor de base de datos cubre tanto la persistencia relacional (recetas,
  interacciones, pacientes anonimizados) como el almacén vectorial para RAG
  (embeddings de fichas técnicas AEMPS/CIMA), evitando introducir un segundo sistema
  (p. ej. un vector store dedicado) solo para el caso de uso de `RAGPharmAgent`.
- `pgvector` soporta búsqueda por similitud (coseno/L2) directamente en SQL,
  integrable con SQLAlchemy 2.0 y consultable de forma asíncrona vía `asyncpg`.
- Reduce la superficie operativa del proyecto a una sola base de datos que gestionar,
  migrar (`alembic`) y respaldar — relevante dado el alcance académico del TFM.

## Consecuencias

**Positivas**
- El dominio es testeable de forma aislada y no requiere mocks de red ni de base de
  datos para validar reglas clínicas.
- Cambiar de proveedor de modelo (p. ej. sustituir Llama 3.1 local por otro modelo) o
  de motor de persistencia no exige tocar `domain/` ni `use_cases/`.
- Un único stack de base de datos simplifica el despliegue y la evaluación del TFM.

**Negativas / trade-offs asumidos**
- El monolito modular no ofrece escalado independiente por componente; se acepta
  porque el TFM no tiene requisitos de carga que lo justifiquen.
- `pgvector` es menos especializado en búsqueda vectorial a gran escala que un vector
  store dedicado (p. ej. Pinecone, Weaviate); aceptable para el volumen de fichas
  técnicas manejado en este proyecto.
- Mantener la disciplina de "el dominio no importa infraestructura" exige revisión
  continua (vía `ruff` y revisión de código) para no introducir acoplamientos
  accidentales.

## Alternativas consideradas

- **Microservicios por agente**: descartado por sobrecoste operativo (orquestación,
  despliegue, observabilidad distribuida) desproporcionado para el alcance de un TFM.
- **Django + ORM síncrono**: descartado por peor ajuste con operaciones I/O-bound
  concurrentes (llamadas a modelos, consultas vectoriales) frente a FastAPI async.
- **Vector store dedicado externo**: descartado para no duplicar infraestructura de
  persistencia cuando PostgreSQL + `pgvector` cubre el volumen y los requisitos de
  latencia del proyecto.
