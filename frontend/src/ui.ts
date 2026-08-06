/**
 * Fragmentos HTML compartidos entre las 3 vistas: badges de severidad/veredicto/latencia,
 * chips de procedencia de los datos, tarjetas de interacción y skeletons de carga. Todo el
 * texto interpolado pasa por `escapeHtml` — la API es de confianza, pero el nombre de
 * fármaco que el propio usuario escribe en el formulario de interacciones se refleja en el
 * DOM sin pasar por el backend, así que no puede quedar sin escapar.
 */

import type { InteractionResult, Severity, SourceKind, InteractionSourceKind, Verdict } from "./types";

export function escapeHtml(value: string): string {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

const SEVERITY_STYLE: Record<string, { classes: string; label: string }> = {
  LOW: { classes: "bg-safe-50 text-safe-700 border-safe-200", label: "BAJA" },
  MEDIUM: { classes: "bg-warning-50 text-warning-700 border-warning-200", label: "MEDIA" },
  HIGH: { classes: "bg-critical-50 text-critical-700 border-critical-200", label: "ALTA" },
  SEVERE: { classes: "bg-critical-50 text-critical-700 border-critical-200", label: "GRAVE" },
};

const VERDICT_STYLE: Record<string, { classes: string; label: string }> = {
  apto: { classes: "bg-safe-100 text-safe-800", label: "✅ APTO" },
  apto_con_precaucion: { classes: "bg-warning-100 text-warning-800", label: "⚠️ APTO CON PRECAUCIÓN" },
  requiere_revision_medica: { classes: "bg-critical-100 text-critical-800", label: "🛑 REQUIERE REVISIÓN MÉDICA" },
};

const SOURCE_STYLE: Record<string, { classes: string; label: string }> = {
  cache: { classes: "bg-verified-50 text-verified-700 border-verified-200", label: "🗄️ Caché vectorial" },
  live: { classes: "bg-live-50 text-live-700 border-live-200", label: "🌐 CIMA en vivo" },
  none: { classes: "bg-neutral-100 text-neutral-500 border-neutral-200", label: "Sin fuente verificada" },
  curated: { classes: "bg-verified-50 text-verified-700 border-verified-200", label: "🗄️ Base curada" },
  llm: { classes: "bg-live-50 text-live-700 border-live-200", label: "🤖 Razonamiento LLM" },
};

const SEVERITY_BORDER: Record<string, string> = {
  LOW: "border-l-safe-600",
  MEDIUM: "border-l-warning-600",
  HIGH: "border-l-critical-600",
  SEVERE: "border-l-critical-600",
};

export function severityBadge(severity: Severity | string): string {
  const style = SEVERITY_STYLE[severity] ?? {
    classes: "bg-slate-100 text-slate-600 border-slate-200",
    label: severity,
  };
  return `<span class="inline-block rounded-full border px-3 py-0.5 text-xs font-bold tracking-wide ${style.classes}">${style.label}</span>`;
}

export function verdictBanner(verdict: Verdict | string): string {
  const style = VERDICT_STYLE[verdict] ?? { classes: "bg-slate-100 text-slate-700", label: verdict };
  return `<span class="inline-block rounded-full px-4 py-1 text-sm font-bold ${style.classes}">${style.label}</span>`;
}

export function sourceChip(source: SourceKind | InteractionSourceKind | string): string {
  const style = SOURCE_STYLE[source] ?? {
    classes: "bg-slate-100 text-slate-500 border-slate-200",
    label: source,
  };
  return `<span class="inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style.classes}">${style.label}</span>`;
}

export function latencyBadge(elapsedMs: number, engineLabel: string): string {
  return `<span class="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-3 py-0.5 font-mono text-xs font-semibold text-sky-700">⚡ ${Math.round(elapsedMs)}ms · ${escapeHtml(engineLabel)}</span>`;
}

/**
 * CIMA no expone ningún endpoint de interacciones farmacológicas — solo fichas técnicas y
 * prospectos. Cuando ninguna combinación de la petición está en la base curada interna, el
 * veredicto completo viene del razonamiento libre de un LLM, sin verificación contra ninguna
 * base de datos clínica oficial. Mostrar esto explícito, no solo como un chip pequeño, para
 * que nunca se confunda con un dato verificado por la AEMPS.
 */
export function llmOnlyDisclaimerHtml(): string {
  return `
    <div class="flex items-start gap-2 rounded-xl border border-warning-200 bg-warning-50 p-3 text-sm text-warning-800">
      <span>⚠️</span>
      <p>
        Ninguno de estos fármacos está en la base curada interna. Este resultado es
        <strong>razonamiento de un modelo de lenguaje</strong>, no un dato verificado contra
        CIMA/AEMPS (que no publica un registro de interacciones) ni contra ninguna base de
        datos clínica oficial — puede variar en fraseo entre consultas y debe confirmarse
        siempre con un profesional sanitario.
      </p>
    </div>`;
}

export function interactionCardHtml(interaction: InteractionResult): string {
  const border = SEVERITY_BORDER[interaction.severity] ?? "border-l-neutral-400";
  return `
    <div class="rounded-xl border border-slate-200 border-l-4 ${border} bg-white p-4 shadow-sm">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        ${severityBadge(interaction.severity)}
        ${sourceChip(interaction.source)}
      </div>
      <p class="font-semibold text-slate-900">${escapeHtml(interaction.primary_drug)} + ${escapeHtml(interaction.secondary_drug)}</p>
      <p class="mt-1 text-sm text-slate-600">${escapeHtml(interaction.description)}</p>
      <p class="mt-2 text-sm text-slate-700"><span class="font-semibold">Recomendación clínica:</span> ${escapeHtml(interaction.clinical_recommendation)}</p>
    </div>`;
}

export function skeletonCardHtml(): string {
  return `
    <div class="animate-pulse space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="h-3 w-1/3 rounded bg-slate-200"></div>
      <div class="h-3 w-full rounded bg-slate-200"></div>
      <div class="h-3 w-5/6 rounded bg-slate-200"></div>
    </div>`;
}

export function skeletonListHtml(count: number): string {
  return Array.from({ length: count }, () => skeletonCardHtml()).join("");
}
