/**
 * Historial de consultas persistido en `localStorage` (zero-friction UX: sobrevive a
 * recargar la página, sin backend ni login). Solo se guardan consultas del RAG clínico —
 * ver `viewConsult.ts`.
 */

export interface HistoryEntry {
  query: string;
  drugName: string | null;
  timestamp: number;
}

const HISTORY_KEY = "pharmagent_history";
const MAX_HISTORY = 8;

export function loadHistory(): HistoryEntry[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function pushHistory(query: string, drugName: string | null): HistoryEntry[] {
  const current = loadHistory().filter((entry) => entry.query !== query);
  current.unshift({ query, drugName, timestamp: Date.now() });
  const trimmed = current.slice(0, MAX_HISTORY);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
  return trimmed;
}

export function clearHistory(): void {
  window.localStorage.removeItem(HISTORY_KEY);
}
