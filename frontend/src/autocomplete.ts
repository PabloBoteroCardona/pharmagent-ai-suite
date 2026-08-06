/**
 * Autocompletado de nombres de fármaco sobre `<input list="...">` + `<datalist>` nativos del
 * navegador, alimentado por `POST /search` (misma búsqueda semántica + respaldo CIMA en vivo
 * que ya usan el resto de vistas). Con debounce y una longitud mínima de consulta para no
 * disparar una petición (y una posible indexación en CIMA) en cada pulsación de tecla.
 */

import { searchDrugs } from "./api";
import { escapeHtml } from "./ui";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 3;
const MAX_SUGGESTIONS = 6;

export interface DrugSuggestions {
  /** Descarta cualquier búsqueda pendiente y vacía el `<datalist>`. Necesario porque asignar
   * `input.value = ""` por código (al enviar el formulario, al pulsar "Limpiar") no dispara el
   * evento `input` del navegador — sin esto, las sugerencias del fármaco anterior se quedaban
   * ahí hasta que el usuario tecleaba de nuevo el mínimo de caracteres. */
  clear: () => void;
}

export function attachDrugSuggestions(input: HTMLInputElement, datalist: HTMLDataListElement): DrugSuggestions {
  let timeoutId: number | undefined;

  const clear = (): void => {
    window.clearTimeout(timeoutId);
    datalist.innerHTML = "";
  };

  input.addEventListener("input", () => {
    const query = input.value.trim();
    window.clearTimeout(timeoutId);

    if (query.length < MIN_QUERY_LENGTH) {
      datalist.innerHTML = "";
      return;
    }

    timeoutId = window.setTimeout(() => {
      void searchDrugs(query, MAX_SUGGESTIONS)
        .then(({ data }) => {
          const uniqueNames = Array.from(new Set(data.results.map((drug) => drug.nombre)));
          datalist.innerHTML = uniqueNames
            .map((nombre) => `<option value="${escapeHtml(nombre)}"></option>`)
            .join("");
        })
        .catch(() => {
          // Sugerencia de autocompletado, no una acción crítica: si falla, no interrumpimos
          // al usuario con un toast — simplemente no hay sugerencias esta vez.
        });
    }, DEBOUNCE_MS);
  });

  return { clear };
}
