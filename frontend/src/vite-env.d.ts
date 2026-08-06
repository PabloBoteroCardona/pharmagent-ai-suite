/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** "true" en el despliegue público: restringe la pestaña de Receta a ejemplos sintéticos
   * en vez de aceptar fotos reales de desconocidos — ver `viewPrescription.ts`. */
  readonly VITE_DEMO_MODE?: string;
  /** Debe coincidir con `API_KEY` del backend en el despliegue público — ver `api.ts`. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
