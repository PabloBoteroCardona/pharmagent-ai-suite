import { ApiError, checkInteractions } from "./api";
import { GROQ_ENGINE_LABEL } from "./constants";
import { showToast } from "./toast";
import {
  escapeHtml,
  interactionCardHtml,
  latencyBadge,
  llmOnlyDisclaimerHtml,
  skeletonListHtml,
  verdictBanner,
} from "./ui";

export function initInteractionsView(): void {
  const addForm = document.getElementById("interactions-add-form") as HTMLFormElement;
  const drugInput = document.getElementById("interactions-drug-input") as HTMLInputElement;
  const chipsContainer = document.getElementById("interactions-drug-chips") as HTMLDivElement;
  const checkButton = document.getElementById("interactions-check-button") as HTMLButtonElement;
  const results = document.getElementById("interactions-results") as HTMLDivElement;

  let drugs: string[] = [];

  function renderChips(): void {
    chipsContainer.innerHTML = drugs
      .map(
        (drug, index) => `
        <span class="inline-flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pl-3 pr-1.5 text-sm text-slate-700">
          ${escapeHtml(drug)}
          <button type="button" data-remove-index="${index}" class="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700" aria-label="Quitar ${escapeHtml(drug)}">✕</button>
        </span>`,
      )
      .join("");
    checkButton.disabled = drugs.length < 2;
  }

  addForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = drugInput.value.trim();
    if (!value) return;
    drugs.push(value);
    drugInput.value = "";
    renderChips();
  });

  chipsContainer.addEventListener("click", (event) => {
    const target = event.target as HTMLElement;
    const indexAttr = target.getAttribute("data-remove-index");
    if (indexAttr === null) return;
    drugs = drugs.filter((_, index) => index !== Number(indexAttr));
    renderChips();
  });

  checkButton.addEventListener("click", () => {
    void (async () => {
      results.innerHTML = skeletonListHtml(2);
      try {
        const { data, elapsedMs } = await checkInteractions(drugs);
        const cardsHtml = data.interactions.length
          ? data.interactions.map(interactionCardHtml).join("")
          : '<p class="text-sm text-emerald-700">No se han detectado interacciones conocidas entre los fármacos seleccionados.</p>';
        const anyLlmSourced = data.interactions.some((i) => i.source === "llm");
        results.innerHTML = `
          <div class="flex flex-wrap items-center gap-2">
            ${verdictBanner(data.verdict)}
            ${latencyBadge(elapsedMs, GROQ_ENGINE_LABEL)}
          </div>
          ${anyLlmSourced ? llmOnlyDisclaimerHtml() : ""}
          ${cardsHtml}`;
      } catch (error) {
        results.innerHTML = "";
        showToast(error instanceof ApiError ? error.message : "Error verificando interacciones.");
      }
    })();
  });

  renderChips();
}
