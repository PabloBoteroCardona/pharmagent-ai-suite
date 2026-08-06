import { ApiError, processPrescription, searchDrugs } from "./api";
import { GEMINI_ENGINE_LABEL } from "./constants";
import { showToast } from "./toast";
import type { ExtractedDrugItem, ProcessPrescriptionResponse } from "./types";
import {
  escapeHtml,
  interactionCardHtml,
  latencyBadge,
  llmOnlyDisclaimerHtml,
  skeletonCardHtml,
  sourceChip,
  verdictBanner,
} from "./ui";

function renderExtraction(data: ProcessPrescriptionResponse, elapsedMs: number): string {
  const drugsHtml = data.prescription.drugs.length
    ? data.prescription.drugs
        .map(
          (drug) => `
        <div class="rounded-xl border border-slate-200 border-l-4 border-l-sky-600 bg-white p-4 shadow-sm">
          <p class="font-semibold text-slate-900">${escapeHtml(drug.farmaco)}</p>
          <p class="mt-1 text-sm text-slate-600">
            Dosificación: ${escapeHtml(drug.dosificacion ?? "no especificada")} ·
            Frecuencia: ${escapeHtml(drug.frecuencia ?? "no especificada")} ·
            Duración: ${escapeHtml(drug.duracion ?? "no especificada")}
          </p>
        </div>`,
        )
        .join("")
    : '<p class="text-sm text-warning-700">No se identificó ningún fármaco en la imagen.</p>';

  const warningsHtml = data.prescription.advertencias
    .map((warning) => `<p class="rounded-lg bg-warning-50 px-3 py-2 text-sm text-warning-800">${escapeHtml(warning)}</p>`)
    .join("");

  const safety = data.safety_check;
  const safetyHtml =
    safety === null
      ? '<p class="text-sm text-slate-500">No se requiere verificación de interacciones: se detectó menos de 2 fármacos en la receta.</p>'
      : `
        <div class="flex flex-wrap items-center gap-2">${verdictBanner(safety.verdict)}</div>
        ${safety.interactions.some((i) => i.source === "llm") ? `<div class="mt-2">${llmOnlyDisclaimerHtml()}</div>` : ""}
        <div class="mt-2 space-y-2">
          ${
            safety.interactions.length
              ? safety.interactions.map(interactionCardHtml).join("")
              : '<p class="text-sm text-safe-700">No se han detectado interacciones conocidas entre los fármacos.</p>'
          }
        </div>`;

  return `
    <div class="flex flex-wrap gap-2">${latencyBadge(elapsedMs, GEMINI_ENGINE_LABEL)}</div>
    <div>
      <h3 class="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">💊 Fármacos extraídos</h3>
      <div class="space-y-2">${drugsHtml}</div>
      ${warningsHtml ? `<div class="mt-2 space-y-2">${warningsHtml}</div>` : ""}
    </div>
    <div>
      <h3 class="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">🛡️ Auditoría de seguridad</h3>
      ${safetyHtml}
    </div>
    <div>
      <h3 class="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">📚 Información CIMA</h3>
      <div id="prescription-cima-list" class="space-y-2"></div>
    </div>`;
}

/** Modo demo (activado vía `VITE_DEMO_MODE=true` en el despliegue público): restringe la
 * pestaña de Receta a un puñado de imágenes de ejemplo sintéticas en vez de aceptar fotos
 * reales de desconocidos. Ver README.md, sección "Descripción y objetivos", para el porqué:
 * una foto de receta real puede contener datos identificativos del paciente, y la única
 * mitigación de verdad frente a eso es no aceptar fotos reales de visitantes anónimos. */
function isDemoMode(): boolean {
  return import.meta.env.VITE_DEMO_MODE === "true";
}

async function runProcessPrescription(file: File, results: HTMLDivElement): Promise<void> {
  results.innerHTML = skeletonCardHtml();
  try {
    const { data, elapsedMs } = await processPrescription(file);
    results.innerHTML = renderExtraction(data, elapsedMs);
    await Promise.all(data.prescription.drugs.map((drug) => attachCimaCard(drug, results)));
  } catch (error) {
    results.innerHTML = "";
    showToast(error instanceof ApiError ? error.message : "Error procesando la receta.");
  }
}

async function attachCimaCard(drug: ExtractedDrugItem, resultsRoot: HTMLElement): Promise<void> {
  const list = resultsRoot.querySelector("#prescription-cima-list");
  if (!list || !drug.farmaco) return;

  const card = document.createElement("div");
  card.innerHTML = skeletonCardHtml();
  list.appendChild(card);

  try {
    const { data } = await searchDrugs(drug.farmaco, 1);
    const hit = data.results[0];
    card.className = "rounded-xl border border-slate-200 border-l-4 border-l-verified-600 bg-white p-4 shadow-sm";
    card.innerHTML = hit
      ? `
        <div class="mb-1 flex items-center gap-2">
          <p class="font-semibold text-slate-900">${escapeHtml(hit.nombre)}</p>
          ${sourceChip(data.source)}
        </div>
        <p class="font-mono text-xs text-slate-400">nº registro ${escapeHtml(hit.nregistro)}</p>
        <p class="mt-1 text-sm text-slate-600">Principios activos: ${escapeHtml(hit.pactivos ?? "—")}</p>
        <p class="text-sm text-slate-600">Laboratorio titular: ${escapeHtml(hit.labtitular ?? "—")}</p>`
      : `<p class="text-sm text-slate-500"><span class="font-semibold">${escapeHtml(drug.farmaco)}</span> — no encontrado en CIMA.</p>`;
  } catch {
    // Degradación silenciosa: una búsqueda CIMA fallida para un fármaco no debe romper el
    // resto de la vista, que ya mostró la extracción y la auditoría de seguridad.
    card.remove();
  }
}

function initDemoMode(results: HTMLDivElement): void {
  const uploadSection = document.getElementById("prescription-upload-section") as HTMLDivElement;
  const demoSection = document.getElementById("prescription-demo-section") as HTMLDivElement;
  const demoStatus = document.getElementById("prescription-demo-status") as HTMLParagraphElement;
  uploadSection.classList.add("hidden");
  demoSection.classList.remove("hidden");

  const sampleButtons = demoSection.querySelectorAll<HTMLButtonElement>("[data-sample]");
  sampleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const url = button.dataset.sample as string;
      const filename = url.split("/").pop() as string;

      void (async () => {
        sampleButtons.forEach((b) => (b.disabled = true));
        demoStatus.textContent = "Cargando imagen de ejemplo…";
        try {
          const response = await fetch(url);
          const blob = await response.blob();
          const file = new File([blob], filename, { type: blob.type });
          demoStatus.textContent = "";
          await runProcessPrescription(file, results);
        } catch {
          demoStatus.textContent = "No se pudo cargar la imagen de ejemplo.";
        } finally {
          sampleButtons.forEach((b) => (b.disabled = false));
        }
      })();
    });
  });
}

export function initPrescriptionView(): void {
  const form = document.getElementById("prescription-form") as HTMLFormElement;
  const fileInput = document.getElementById("prescription-file") as HTMLInputElement;
  const filenameLabel = document.getElementById("prescription-filename") as HTMLSpanElement;
  const preview = document.getElementById("prescription-preview") as HTMLImageElement;
  const consentCheckbox = document.getElementById("prescription-consent") as HTMLInputElement;
  const submitButton = document.getElementById("prescription-submit") as HTMLButtonElement;
  const clearButton = document.getElementById("prescription-clear") as HTMLButtonElement;
  const results = document.getElementById("prescription-results") as HTMLDivElement;

  if (isDemoMode()) {
    initDemoMode(results);
    clearButton.addEventListener("click", () => {
      results.innerHTML = "";
    });
    return;
  }

  function updateSubmitState(): void {
    const file = fileInput.files?.[0];
    submitButton.disabled = !file || !consentCheckbox.checked;
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    filenameLabel.textContent = file ? file.name : "Ningún archivo seleccionado";
    if (!file) {
      preview.classList.add("hidden");
    } else {
      preview.src = URL.createObjectURL(file);
      preview.classList.remove("hidden");
    }
    updateSubmitState();
  });

  consentCheckbox.addEventListener("change", updateSubmitState);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const file = fileInput.files?.[0];
    if (!file || !consentCheckbox.checked) return;
    void runProcessPrescription(file, results);
  });

  clearButton.addEventListener("click", () => {
    fileInput.value = "";
    filenameLabel.textContent = "Ningún archivo seleccionado";
    preview.classList.add("hidden");
    preview.src = "";
    consentCheckbox.checked = false;
    submitButton.disabled = true;
    results.innerHTML = "";
  });
}
