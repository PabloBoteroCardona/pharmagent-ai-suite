/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** "true" en el despliegue público: restringe la pestaña de Receta a ejemplos sintéticos
   * en vez de aceptar fotos reales de desconocidos — ver `viewPrescription.ts`. */
  readonly VITE_DEMO_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
