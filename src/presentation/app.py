"""Panel web interactivo de PharmAgent AI Suite, construido con Streamlit.

Cliente HTTP puro sobre la API REST (`src/infrastructure/api`): no importa código de
`infrastructure`/`application` directamente, para poder desplegarse como proceso
independiente (p. ej. en un contenedor separado) que solo necesita conocer la URL base de
la API. La API no requiere autenticación (ver .memory/DECISIONS.md, "API REST abierta para
consumo local"), así que este cliente no envía ninguna cabecera de credenciales.

La URL base es transparente para el usuario final: se resuelve de `PHARMAGENT_API_BASE_URL`
si está definida, o `http://localhost:8000` por defecto — no hay ningún control en la
interfaz para cambiarla, a propósito (ver "Limpieza de UX" en .memory/DECISIONS.md).

Lanzamiento: `streamlit run src/presentation/app.py`
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_BASE_URL = os.getenv("PHARMAGENT_API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 60.0

# --- Paleta "grado profesional sanitario" ---
COLOR_AZUL_MEDICO = "#0B5394"
COLOR_AZUL_MEDICO_CLARO = "#1976D2"
COLOR_VERDE_MENTA = "#26A69A"
COLOR_GRIS_OSCURO = "#263238"
COLOR_GRIS_CLARO = "#F4F6F8"
COLOR_VERDE = "#2E7D32"
COLOR_AMARILLO = "#F9A825"
COLOR_ROJO = "#C62828"

SEVERITY_COLOR = {
    "LOW": COLOR_VERDE,
    "MEDIUM": COLOR_AMARILLO,
    "HIGH": COLOR_ROJO,
    "SEVERE": COLOR_ROJO,
}
SEVERITY_LABEL = {
    "LOW": "BAJA",
    "MEDIUM": "MEDIA",
    "HIGH": "ALTA",
    "SEVERE": "GRAVE",
}
VERDICT_COLOR = {
    "apto": COLOR_VERDE,
    "apto_con_precaucion": COLOR_AMARILLO,
    "requiere_revision_medica": COLOR_ROJO,
}
VERDICT_LABEL = {
    "apto": "✅ APTO",
    "apto_con_precaucion": "⚠️ APTO CON PRECAUCIÓN",
    "requiere_revision_medica": "🛑 REQUIERE REVISIÓN MÉDICA",
}


def _init_session_state() -> None:
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("interaction_drugs", [])


def api_post(
    path: str,
    *,
    json: dict | None = None,
    files: dict | None = None,
) -> dict | None:
    """POST a la API REST; en error muestra `st.error` y devuelve `None`."""
    url = f"{API_BASE_URL}{path}"
    try:
        response = httpx.post(
            url, json=json, files=files, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"Error {exc.response.status_code} en {path}: {exc.response.text}")
    except httpx.RequestError as exc:
        st.error(f"No se pudo conectar con la API en {url}: {exc}")
    return None


def check_api_health() -> bool:
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
        return response.status_code == 200
    except httpx.RequestError:
        return False


def inject_custom_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {COLOR_GRIS_CLARO};
        }}
        h1, h2, h3 {{
            color: {COLOR_GRIS_OSCURO};
        }}
        [data-testid="stSidebar"] {{
            background-color: {COLOR_GRIS_OSCURO};
        }}
        [data-testid="stSidebar"] * {{
            color: #ECEFF1 !important;
        }}
        .stTabs [data-baseweb="tab"] {{
            font-weight: 600;
            color: {COLOR_AZUL_MEDICO};
        }}
        .pharma-card {{
            background-color: white;
            border: 1px solid #DDE3E8;
            border-left: 5px solid {COLOR_AZUL_MEDICO_CLARO};
            border-radius: 8px;
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
        }}
        .pharma-card.rag {{
            border-left-color: {COLOR_VERDE_MENTA};
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.7rem;
            border-radius: 999px;
            color: white;
            font-weight: 700;
            font-size: 0.8rem;
            letter-spacing: 0.02em;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background-color:{color};">{text}</span>'


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 💊 PharmAgent AI Suite")
        st.caption("Panel clínico asistido por IA — TFM")

        st.markdown("### 🩺 Estado de los servicios")
        if st.button("🔄 Comprobar conexión", use_container_width=True):
            st.session_state["api_healthy"] = check_api_health()

        healthy = st.session_state.get("api_healthy")
        if healthy is None:
            st.info("Estado sin comprobar todavía.")
        elif healthy:
            st.success("API operativa (/health → 200 OK)")
        else:
            st.error("API no disponible")

        st.markdown("---")
        st.markdown(
            "**Módulos**\n"
            "- 📋 Flujo asistencial integrado\n"
            "- 💬 Consulta clínica RAG\n"
            "- 🛡️ Verificador de interacciones\n"
        )
        st.caption("Fuente de datos clínicos: CIMA (AEMPS)")


def render_prescription_tab() -> None:
    st.subheader("📋 Flujo Asistencial Integrado (Receta Completa)")
    st.caption(
        "Sube una foto de la receta para extraer los fármacos, auditar su seguridad "
        "y consultar información oficial de CIMA (AEMPS) de cada uno."
    )

    uploaded_file = st.file_uploader(
        "Arrastra o selecciona la foto de la receta",
        type=["png", "jpg", "jpeg", "webp"],
    )

    if uploaded_file is not None:
        st.image(uploaded_file, caption="Receta cargada", width=320)

    if st.button("🔎 Procesar receta", type="primary", disabled=uploaded_file is None):
        with st.spinner("Analizando receta y verificando seguridad clínica…"):
            image_bytes = uploaded_file.getvalue()
            result = api_post(
                "/api/v1/pharmacy/process-prescription",
                files={
                    "file": (
                        uploaded_file.name,
                        image_bytes,
                        uploaded_file.type or "image/jpeg",
                    )
                },
            )
        if result is not None:
            st.session_state["prescription_result"] = result

    result = st.session_state.get("prescription_result")
    if not result:
        return

    prescription = result.get("prescription", {})
    drugs = prescription.get("drugs", [])
    advertencias = prescription.get("advertencias", [])

    st.markdown("#### 💊 Fármacos extraídos")
    if not drugs:
        st.warning("No se identificó ningún fármaco en la imagen.")
    for drug in drugs:
        st.markdown(
            f"""
            <div class="pharma-card">
                <strong>{drug.get("farmaco", "—")}</strong><br>
                Dosificación: {drug.get("dosificacion") or "no especificada"} ·
                Frecuencia: {drug.get("frecuencia") or "no especificada"} ·
                Duración: {drug.get("duracion") or "no especificada"}
            </div>
            """,
            unsafe_allow_html=True,
        )
    for advertencia in advertencias:
        st.warning(advertencia)

    st.markdown("#### 🛡️ Auditoría de Seguridad")
    safety_check = result.get("safety_check")
    if safety_check is None:
        st.info(
            "No se requiere verificación de interacciones: se detectó menos de 2 "
            "fármacos en la receta."
        )
    else:
        verdict = safety_check.get("verdict", "")
        st.markdown(
            badge(
                VERDICT_LABEL.get(verdict, verdict),
                VERDICT_COLOR.get(verdict, COLOR_GRIS_OSCURO),
            ),
            unsafe_allow_html=True,
        )
        interactions = safety_check.get("interactions", [])
        if not interactions:
            st.success(
                "No se han detectado interacciones conocidas entre los fármacos."
            )
        for interaction in interactions:
            severity = interaction.get("severity", "")
            st.markdown(
                f"""
                <div class="pharma-card">
                    {badge(SEVERITY_LABEL.get(severity, severity), SEVERITY_COLOR.get(severity, COLOR_GRIS_OSCURO))}
                    <strong>&nbsp;{interaction.get("primary_drug")} + {interaction.get("secondary_drug")}</strong><br>
                    {interaction.get("description", "")}<br>
                    <em>Recomendación clínica:</em> {interaction.get("clinical_recommendation", "")}
                    <div style="color:#78909C; font-size:0.8rem; margin-top:0.3rem;">
                        Fuente: {interaction.get("source", "curated")}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if drugs:
        st.markdown("#### 📚 Información RAG de CIMA")
        for drug in drugs:
            nombre = drug.get("farmaco", "")
            if not nombre:
                continue
            search_result = api_post(
                "/api/v1/pharmacy/search", json={"query": nombre, "limit": 1}
            )
            hits = (search_result or {}).get("results", [])
            if hits:
                hit = hits[0]
                st.markdown(
                    f"""
                    <div class="pharma-card rag">
                        <strong>{hit.get("nombre")}</strong>
                        <span style="color:#78909C;"> (nº registro {hit.get("nregistro")})</span><br>
                        Principios activos: {hit.get("pactivos") or "—"}<br>
                        Laboratorio titular: {hit.get("labtitular") or "—"}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="pharma-card rag">
                        <strong>{nombre}</strong> — no encontrado en CIMA.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def render_consult_tab() -> None:
    st.subheader("💬 Consulta Clínica RAG & Chat")
    st.caption(
        "Pregunta libremente sobre cualquier medicamento; las respuestas se apoyan en "
        "la información oficial de CIMA/AEMPS."
    )

    # Streamlit prohíbe reasignar el `session_state` de un widget en la misma ejecución
    # en que ya se instanció (`StreamlitAPIException`) — por eso la limpieza no puede
    # hacerse justo después de usarlo más abajo. Se difiere aquí, antes de instanciar el
    # widget, marcada por un flag puesto en la ejecución anterior tras enviar la pregunta.
    if st.session_state.get("_clear_drug_name_hint"):
        st.session_state["consult_drug_name"] = ""
        st.session_state["_clear_drug_name_hint"] = False

    drug_name_hint = st.text_input(
        "Nombre del fármaco (opcional, acota la búsqueda en CIMA solo para tu próxima "
        "pregunta — se vacía automáticamente después de enviarla)",
        key="consult_drug_name",
    )

    for message in st.session_state["chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("drug_name"):
                st.caption(f"🔎 Búsqueda en CIMA acotada a: {message['drug_name']}")
            if message.get("sources"):
                with st.expander("Fuentes CIMA / AEMPS"):
                    for source in message["sources"]:
                        st.markdown(f"- {source}")

    query = st.chat_input("Escribe tu consulta clínica…")
    if query:
        st.session_state["chat_messages"].append(
            {"role": "user", "content": query, "drug_name": drug_name_hint or None}
        )
        with st.chat_message("user"):
            st.markdown(query)
            if drug_name_hint:
                st.caption(f"🔎 Búsqueda en CIMA acotada a: {drug_name_hint}")

        with st.chat_message("assistant"):
            with st.spinner("Consultando base de conocimiento clínico…"):
                payload = {"query": query}
                if drug_name_hint:
                    payload["drug_name"] = drug_name_hint
                result = api_post("/api/v1/pharmacy/consult", json=payload)

            if result is not None:
                st.markdown(result.get("response", ""))
                sources = result.get("sources", [])
                if sources:
                    with st.expander("Fuentes CIMA / AEMPS"):
                        for source in sources:
                            st.markdown(f"- {source}")
                st.caption(f"Procedencia de los datos: {result.get('source', 'none')}")
                st.session_state["chat_messages"].append(
                    {
                        "role": "assistant",
                        "content": result.get("response", ""),
                        "sources": sources,
                    }
                )

        # El campo "Nombre del fármaco" es un filtro de una sola pregunta, no contexto
        # de conversación persistente: si quedara "pegado" en session_state, preguntas
        # posteriores sobre otro fármaco seguirían buscando el nombre antiguo en CIMA (y
        # fallarían en silencio, con una respuesta que parece "no sé nada de X" cuando en
        # realidad buscó "Y") — bug real reportado por el usuario. Se marca aquí para que
        # se vacíe al principio de la próxima ejecución (ver comentario más arriba).
        st.session_state["_clear_drug_name_hint"] = True
        st.rerun()


def render_interactions_tab() -> None:
    st.subheader("🛡️ Verificador Rápido de Interacciones")
    st.caption("Selecciona 2 o más fármacos para comprobar interacciones conocidas.")

    with st.form("add_drug_form", clear_on_submit=True):
        col_input, col_button = st.columns([4, 1])
        new_drug = col_input.text_input(
            "Nombre del fármaco", label_visibility="collapsed"
        )
        add_clicked = col_button.form_submit_button(
            "➕ Añadir", use_container_width=True
        )
        if add_clicked and new_drug.strip():
            st.session_state["interaction_drugs"].append(new_drug.strip())

    if st.session_state["interaction_drugs"]:
        st.markdown("**Fármacos seleccionados:**")
        for idx, drug_name in enumerate(st.session_state["interaction_drugs"]):
            col_name, col_remove = st.columns([5, 1])
            col_name.markdown(f"- {drug_name}")
            if col_remove.button("✖", key=f"remove_drug_{idx}"):
                st.session_state["interaction_drugs"].pop(idx)
                st.rerun()

    can_check = len(st.session_state["interaction_drugs"]) >= 2
    if st.button("🛡️ Verificar interacciones", type="primary", disabled=not can_check):
        with st.spinner("Verificando interacciones conocidas…"):
            result = api_post(
                "/api/v1/pharmacy/check-interactions",
                json={"drugs": st.session_state["interaction_drugs"]},
            )
        if result is not None:
            st.session_state["interaction_result"] = result
    elif not can_check:
        st.info("Añade al menos 2 fármacos para poder verificar interacciones.")

    result = st.session_state.get("interaction_result")
    if not result:
        return

    verdict = result.get("verdict", "")
    st.markdown(
        badge(
            VERDICT_LABEL.get(verdict, verdict),
            VERDICT_COLOR.get(verdict, COLOR_GRIS_OSCURO),
        ),
        unsafe_allow_html=True,
    )
    interactions = result.get("interactions", [])
    if not interactions:
        st.success(
            "No se han detectado interacciones conocidas entre los fármacos seleccionados."
        )
    for interaction in interactions:
        severity = interaction.get("severity", "")
        st.markdown(
            f"""
            <div class="pharma-card">
                {badge(SEVERITY_LABEL.get(severity, severity), SEVERITY_COLOR.get(severity, COLOR_GRIS_OSCURO))}
                <strong>&nbsp;{interaction.get("primary_drug")} + {interaction.get("secondary_drug")}</strong><br>
                {interaction.get("description", "")}<br>
                <em>Recomendación clínica:</em> {interaction.get("clinical_recommendation", "")}
                <div style="color:#78909C; font-size:0.8rem; margin-top:0.3rem;">
                    Fuente: {interaction.get("source", "curated")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="PharmAgent AI Suite",
        page_icon="💊",
        layout="wide",
    )
    _init_session_state()
    inject_custom_css()
    render_sidebar()

    st.title("💊 PharmAgent AI Suite")
    st.caption(
        "Asistencia farmacológica clínica potenciada por IA, con datos oficiales de CIMA/AEMPS."
    )

    tab_prescription, tab_consult, tab_interactions = st.tabs(
        [
            "📋 Flujo Asistencial Integrado (Receta Completa)",
            "💬 Consulta Clínica RAG & Chat",
            "🛡️ Verificador Rápido de Interacciones",
        ]
    )

    with tab_prescription:
        render_prescription_tab()
    with tab_consult:
        render_consult_tab()
    with tab_interactions:
        render_interactions_tab()


if __name__ == "__main__":
    main()
