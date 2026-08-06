/**
 * Cliente HTTP tipado frente a la API REST de PharmAgent (`src/infrastructure/api`).
 *
 * Desacoplado del backend: solo conoce `API_BASE_URL` y los contratos JSON de
 * `src/infrastructure/api/schemas/drug_schemas.py` (espejados en `types.ts`) — el frontend
 * es un cliente externo más, igual que lo era el panel Streamlit que sustituye.
 */

import type {
  ConsultationResponse,
  DrugSearchResponse,
  InteractionCheckResponse,
  ProcessPrescriptionResponse,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
// Solo se envía si está definida (despliegue público) — en desarrollo local la API no exige
// ninguna, ver `Settings.api_key`/`security.py`. Nota: al vivir en el bundle del frontend,
// cualquiera puede leerla desde las DevTools — frena abuso anónimo, no es un secreto real.
const API_KEY = import.meta.env.VITE_API_KEY;
const REQUEST_TIMEOUT_MS = 60_000;
const HEALTH_TIMEOUT_MS = 5_000;

export class ApiError extends Error {}

export interface ApiResult<T> {
  data: T;
  elapsedMs: number;
}

function buildHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const started = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: buildHeaders(init.headers),
      signal: controller.signal,
    });
    const elapsedMs = performance.now() - started;
    if (!response.ok) {
      const text = await response.text();
      throw new ApiError(`Error ${response.status} en ${path}: ${text}`);
    }
    const data = (await response.json()) as T;
    return { data, elapsedMs };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Tiempo de espera agotado consultando ${path}.`);
    }
    throw new ApiError(`No se pudo conectar con la API en ${API_BASE_URL}: ${(error as Error).message}`);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function postJson<T>(path: string, body: unknown): Promise<ApiResult<T>> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function checkHealth(): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function consult(query: string, drugName?: string): Promise<ApiResult<ConsultationResponse>> {
  return postJson<ConsultationResponse>(
    "/api/v1/pharmacy/consult",
    drugName ? { query, drug_name: drugName } : { query },
  );
}

export function searchDrugs(query: string, limit = 1): Promise<ApiResult<DrugSearchResponse>> {
  return postJson<DrugSearchResponse>("/api/v1/pharmacy/search", { query, limit });
}

export function checkInteractions(drugs: string[]): Promise<ApiResult<InteractionCheckResponse>> {
  return postJson<InteractionCheckResponse>("/api/v1/pharmacy/check-interactions", { drugs });
}

export function processPrescription(file: File): Promise<ApiResult<ProcessPrescriptionResponse>> {
  const formData = new FormData();
  formData.append("file", file);
  return request<ProcessPrescriptionResponse>("/api/v1/pharmacy/process-prescription", {
    method: "POST",
    body: formData,
  });
}
