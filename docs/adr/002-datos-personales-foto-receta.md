# ADR 002 — Tratamiento de datos personales en la foto de receta médica

## Estado

Aceptado — 2026-08-06.

## Contexto

`PrescriptionAgent` usa Gemini (comprensión multimodal) para extraer los fármacos de una
foto de receta. A diferencia de otras rutas del sistema — que solo envían a un proveedor
externo nombres de fármaco y fragmentos de ficha técnica (ver [ADR 001](001-stack-python-adk.md)
y [README.md](../../README.md#descripción-y-objetivos)) — aquí se envía la **imagen
completa** a un tercero (Google). Una receta médica real en España habitualmente incluye
datos identificativos directos del paciente (nombre, a veces DNI/NIE, dirección) y del
prescriptor: no es solo "dato de salud" en abstracto, es categoría especial (art. 9 RGPD)
combinada con identificación directa de una persona.

Se planteó explícitamente si un aviso en la interfaz más una casilla de confirmación ("he
tapado los datos identificativos") sería suficiente, de cara a un despliegue público, para
desplazar la responsabilidad legal a quien sube la foto. Conclusión del análisis (esto no es
asesoría legal, es el entendimiento que sustenta la decisión de diseño): bajo RGPD/LOPDGDD,
quien opera el servicio es el **responsable del tratamiento** — determina los medios (usar
Gemini) y los fines (extraer fármacos) — y esa responsabilidad no se transfiere por el
consentimiento o la advertencia dados al usuario final. Una casilla de confirmación reduce
el riesgo y es evidencia de diligencia (privacidad desde el diseño, art. 25 RGPD), pero no
es una cláusula de exención de responsabilidad; y para datos de salud el RGPD exige
consentimiento explícito e informado del propio interesado (el paciente), no una casilla
genérica marcada por un tercero que sube el archivo.

El proyecto ya declara como principio de diseño transversal que los datos de salud reciben
tratamiento especialmente cuidadoso (embeddings 100% locales, ver ADR 001). Desplegar la
función de foto de receta abierta a cualquier visitante público sin más contradiría ese
principio en la práctica, aunque se documentara bien.

## Decisión

Diferenciar el comportamiento según el entorno, activado por la variable de entorno
`VITE_DEMO_MODE` del frontend (ver `frontend/.env.example`, `frontend/src/viewPrescription.ts`):

### 1. Despliegue público (`VITE_DEMO_MODE=true`)

La pestaña "Receta" **no acepta ninguna foto subida por el visitante**. En su lugar ofrece 3
imágenes de ejemplo 100% sintéticas — generadas con el script ya existente
[evaluation/generate_synthetic_prescriptions.py](../../evaluation/generate_synthetic_prescriptions.py)
(texto renderizado sobre fondo blanco, sin ninguna receta ni paciente real) — copiadas a
`frontend/public/samples/`. Los tres casos cubren 1, 2 y 3 fármacos, incluyendo uno con una
interacción `SEVERE` real (warfarina + aspirina) para que la demo sea representativa del
flujo completo (extracción + auditoría de interacciones + ficha CIMA).

Esto **elimina el riesgo en origen** en vez de intentar gestionarlo con avisos: no puede
llegar a Google ninguna imagen real de nadie, porque no se acepta ninguna.

### 2. Desarrollo local (`VITE_DEMO_MODE` sin definir)

Se mantiene la subida real — necesaria para seguir desarrollando y probando la extracción
contra imágenes reales —, con mitigaciones en profundidad. Ninguna es suficiente por sí
sola, y se documentan como tal, no como solución completa:

- La imagen nunca se persiste (ni en base de datos ni en logs) — solo el resultado extraído
  (`ProcessPrescriptionUseCase` escribe fármacos/advertencias/veredicto, nunca la imagen).
- El *system prompt* de `GeminiClient` instruye explícitamente a no incluir ningún dato
  identificativo en la respuesta, aunque sea legible en la imagen.
- El frontend exige una casilla de confirmación explícita antes de habilitar el envío, con
  aviso visible de que la imagen sale a un proveedor externo.

## Consecuencias

**Positivas**
- El despliegue público queda sin superficie de riesgo real de filtración de datos de
  pacientes reales a un tercero — no depende de que cada visitante haga caso a un aviso.
- La demo pública sigue mostrando el flujo completo del producto, no una versión recortada.
- El desarrollo local conserva la capacidad de probar contra imágenes reales cuando hace
  falta, con las mitigaciones que ya existían.

**Negativas / trade-offs asumidos**
- Quien visite el despliegue público no puede probar la extracción con su propia receta — se
  acepta como coste necesario, no como una limitación técnica accidental.
- Las mitigaciones de modo local (prompt reforzado, no persistencia, casilla de confirmación)
  no eliminan el riesgo estructural de que Google procese la imagen completa en sus
  servidores antes de que cualquier filtro propio pueda actuar. Un uso real con pacientes
  reales, más allá de desarrollo/demo, necesitaría un acuerdo de encargado de tratamiento con
  Google y muy probablemente una Evaluación de Impacto relativa a la Protección de Datos
  (EIPD/DPIA).

## Alternativas consideradas

- **Solo aviso + casilla de confirmación, sin modo demo, también en público**: descartada
  como mitigación única para el despliegue público — reduce el riesgo pero no cambia quién es
  el responsable legal del tratamiento ante una inspección. Se conserva como defensa en
  profundidad para desarrollo local, no como solución para un entorno público.
- **Redacción/anonimización automática de la imagen** (detectar y difuminar nombre/DNI antes
  de enviarla a Gemini): descartada por ahora — exigiría un pipeline de visión por computador
  propio y fiable, sin saber de antemano el formato de cada receta, con riesgo real de fallos
  silenciosos que darían una falsa sensación de seguridad peor que no ofrecer la mitigación.
- **No ofrecer la función de foto de receta en el despliegue público en absoluto**:
  descartada por reducir demasiado el valor de la demo — el modo con ejemplos sintéticos
  consigue el mismo objetivo de eliminar el riesgo sin sacrificar mostrar la funcionalidad
  completa del producto.
