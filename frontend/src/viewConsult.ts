import { ApiError, consult } from "./api";
import { attachDrugSuggestions } from "./autocomplete";
import { GROQ_ENGINE_LABEL } from "./constants";
import { renderMarkdown } from "./markdown";
import { showToast } from "./toast";
import type { ConsultationResponse } from "./types";
import { escapeHtml, latencyBadge, skeletonCardHtml, sourceChip } from "./ui";

function consultResultCardHtml(
  query: string,
  drugName: string | null,
  data: ConsultationResponse,
  elapsedMs: number,
): string {
  const sourcesHtml = data.sources.length
    ? `
      <details class="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
        <summary class="cursor-pointer font-semibold text-slate-700">📚 Fuentes CIMA / AEMPS</summary>
        <ul class="mt-2 space-y-1.5">
          ${data.sources
            .map(
              (source) => `
            <li class="flex flex-wrap items-center gap-2">
              <span class="font-semibold">${escapeHtml(source.nombre)}</span>
              ${sourceChip("cache")}
              ${source.ficha_tecnica_url ? `<a class="text-sky-700 underline" href="${escapeHtml(source.ficha_tecnica_url)}" target="_blank" rel="noopener">Ficha técnica</a>` : ""}
              ${source.prospecto_url ? `<a class="text-sky-700 underline" href="${escapeHtml(source.prospecto_url)}" target="_blank" rel="noopener">Prospecto</a>` : ""}
            </li>`,
            )
            .join("")}
        </ul>
      </details>`
    : "";

  return `
    <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p class="text-xs font-semibold text-slate-400">Pregunta${drugName ? ` · acotada a ${escapeHtml(drugName)}` : ""}</p>
      <p class="mb-3 text-sm font-medium text-slate-800">${escapeHtml(query)}</p>
      <div class="mb-3 flex flex-wrap gap-2">
        ${latencyBadge(elapsedMs, GROQ_ENGINE_LABEL)}
        ${sourceChip(data.source)}
      </div>
      <div class="markdown-body text-sm text-slate-700">${renderMarkdown(data.response || "_Sin respuesta._")}</div>
      ${sourcesHtml}
    </article>`;
}

async function runConsult(query: string, drugName: string | null, results: HTMLDivElement): Promise<void> {
  const placeholder = document.createElement("div");
  placeholder.innerHTML = skeletonCardHtml();
  results.prepend(placeholder);

  try {
    const { data, elapsedMs } = await consult(query, drugName ?? undefined);
    placeholder.outerHTML = consultResultCardHtml(query, drugName, data, elapsedMs);
  } catch (error) {
    placeholder.remove();
    showToast(error instanceof ApiError ? error.message : "Error inesperado consultando la API.");
  }
}

export function initConsultView(): void {
  const form = document.getElementById("consult-form") as HTMLFormElement;
  const queryInput = document.getElementById("consult-query") as HTMLInputElement;
  const drugInput = document.getElementById("consult-drug-name") as HTMLInputElement;
  const results = document.getElementById("consult-results") as HTMLDivElement;
  const clearButton = document.getElementById("consult-clear") as HTMLButtonElement;
  const drugSuggestionsList = document.getElementById("consult-drug-suggestions") as HTMLDataListElement;

  const drugSuggestions = attachDrugSuggestions(drugInput, drugSuggestionsList);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;
    const drugName = drugInput.value.trim() || null;
    queryInput.value = "";
    drugInput.value = "";
    drugSuggestions.clear();
    void runConsult(query, drugName, results);
  });

  clearButton.addEventListener("click", () => {
    results.innerHTML = "";
  });
}
