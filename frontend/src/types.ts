/**
 * Espejo en TypeScript de los esquemas Pydantic de `src/infrastructure/api/schemas/drug_schemas.py`.
 * Mantener sincronizado a mano con el backend — no hay generación automática de tipos.
 */

export type SourceKind = "cache" | "live" | "none";
export type InteractionSourceKind = "curated" | "llm";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "SEVERE";
export type Verdict = "apto" | "apto_con_precaucion" | "requiere_revision_medica";

export interface DrugSearchResultItem {
  nregistro: string;
  nombre: string;
  pactivos: string | null;
  labtitular: string | null;
}

export interface DrugSearchResponse {
  results: DrugSearchResultItem[];
  source: SourceKind;
}

export interface ConsultationSourceItem {
  nombre: string;
  ficha_tecnica_url: string | null;
  prospecto_url: string | null;
}

export interface ConsultationResponse {
  query: string;
  response: string;
  sources: ConsultationSourceItem[];
  source: SourceKind;
}

export interface ExtractedDrugItem {
  farmaco: string;
  dosificacion: string | null;
  frecuencia: string | null;
  duracion: string | null;
}

export interface PrescriptionAnalysisResponse {
  drugs: ExtractedDrugItem[];
  advertencias: string[];
}

export interface InteractionResult {
  primary_drug: string;
  secondary_drug: string;
  severity: Severity;
  description: string;
  clinical_recommendation: string;
  source: InteractionSourceKind;
}

export interface InteractionCheckResponse {
  interactions: InteractionResult[];
  verdict: Verdict;
}

export interface ProcessPrescriptionResponse {
  prescription: PrescriptionAnalysisResponse;
  safety_check: InteractionCheckResponse | null;
}
