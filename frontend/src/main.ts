import "./style.css";
import { checkHealth } from "./api";
import { clearHistory, loadHistory } from "./state";
import { escapeHtml } from "./ui";
import { initConsultView } from "./viewConsult";
import { initInteractionsView } from "./viewInteractions";
import { initPrescriptionView } from "./viewPrescription";

let activateTab: (tab: string) => void = () => {};

function initTabs(): void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-tab]"));
  const views = Array.from(document.querySelectorAll<HTMLElement>("[data-view]"));

  activateTab = (tab: string): void => {
    buttons.forEach((button) => button.setAttribute("aria-selected", String(button.dataset.tab === tab)));
    views.forEach((view) => view.classList.toggle("hidden", view.id !== `view-${tab}`));
  };

  buttons.forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab as string));
  });
}

function statusRowHtml(color: string, label: string): string {
  return `<div class="flex items-center gap-2"><span class="h-2 w-2 shrink-0 rounded-full" style="background-color:${color}"></span><span>${label}</span></div>`;
}

async function refreshStatus(): Promise<void> {
  const statusList = document.getElementById("status-list") as HTMLDivElement;
  statusList.innerHTML = statusRowHtml("#94A3B8", "API — comprobando…");
  const healthy = await checkHealth();
  statusList.innerHTML = [
    statusRowHtml(healthy ? "#16A34A" : "#DC2626", healthy ? "API operativa (/health)" : "API no disponible"),
    statusRowHtml("#64748B", "PostgreSQL + pgvector (declarado)"),
    statusRowHtml("#64748B", "Groq · Llama 3.1-8b-instant (declarado)"),
  ].join("");
}

function renderHistory(): void {
  const list = document.getElementById("history-list") as HTMLDivElement;
  const history = loadHistory();
  if (!history.length) {
    list.innerHTML = '<p class="text-xs text-slate-500">Aún no hay consultas en esta sesión.</p>';
    return;
  }
  list.innerHTML = history
    .map(
      (entry, index) => `
      <button
        type="button"
        data-history-index="${index}"
        class="block w-full truncate rounded-lg px-2 py-1.5 text-left text-slate-300 hover:bg-slate-800 hover:text-white"
        title="${escapeHtml(entry.query)}"
      >
        🕘 ${escapeHtml(entry.query)}
      </button>`,
    )
    .join("");

  list.querySelectorAll<HTMLButtonElement>("[data-history-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const entry = history[Number(button.dataset.historyIndex)];
      activateTab("consult");
      const queryInput = document.getElementById("consult-query") as HTMLInputElement;
      const drugInput = document.getElementById("consult-drug-name") as HTMLInputElement;
      queryInput.value = entry.query;
      drugInput.value = entry.drugName ?? "";
      queryInput.focus();
    });
  });
}

function initSidebar(): void {
  document.getElementById("status-refresh")?.addEventListener("click", () => void refreshStatus());
  document.getElementById("history-clear")?.addEventListener("click", () => {
    clearHistory();
    renderHistory();
  });
  void refreshStatus();
  renderHistory();
}

function initMobileSidebarToggle(): void {
  const toggle = document.getElementById("sidebar-toggle") as HTMLButtonElement;
  const sidebar = document.getElementById("sidebar") as HTMLElement;
  toggle.addEventListener("click", () => {
    const isHidden = sidebar.classList.toggle("hidden");
    toggle.setAttribute("aria-expanded", String(!isHidden));
  });
}

initTabs();
initSidebar();
initMobileSidebarToggle();
initConsultView(renderHistory);
initInteractionsView();
initPrescriptionView();
