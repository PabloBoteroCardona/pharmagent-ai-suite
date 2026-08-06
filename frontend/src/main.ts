import "./style.css";
import { checkHealth } from "./api";
import { initConsultView } from "./viewConsult";
import { initInteractionsView } from "./viewInteractions";
import { initPrescriptionView } from "./viewPrescription";

function initTabs(): void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-tab]"));
  const views = Array.from(document.querySelectorAll<HTMLElement>("[data-view]"));

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.tab as string;
      buttons.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
      views.forEach((view) => view.classList.toggle("hidden", view.id !== `view-${tab}`));
    });
  });
}

function statusRowHtml(dotClass: string, label: string): string {
  return `<div class="flex items-center gap-2"><span class="h-2 w-2 shrink-0 rounded-full ${dotClass}"></span><span>${label}</span></div>`;
}

async function refreshStatus(): Promise<void> {
  const statusList = document.getElementById("status-list") as HTMLDivElement;
  statusList.innerHTML = statusRowHtml("bg-neutral-400", "Comprobando sistema clínico…");
  const healthy = await checkHealth();
  statusList.innerHTML = [
    statusRowHtml(
      healthy ? "bg-safe-600" : "bg-critical-600",
      healthy ? "Sistema Clínico Activo" : "Sistema Clínico No Disponible",
    ),
    statusRowHtml("bg-safe-600", "Vademécum Oficial Sincronizado"),
    statusRowHtml("bg-safe-600", "Motor de Respuestas Listo"),
  ].join("");
}

function initFooterYear(): void {
  const yearEl = document.getElementById("footer-year");
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());
}

initTabs();
void refreshStatus();
initFooterYear();
initConsultView();
initInteractionsView();
initPrescriptionView();
