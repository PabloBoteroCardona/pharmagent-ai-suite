"""Script de prueba manual para CimaAPIClient contra la API real de CIMA/AEMPS.

No es parte de la suite automatizada (ver tests/unit/test_cima_client.py, que cubre
CimaAPIClient con dobles) — este script hace peticiones reales a CIMA, útil para
verificación puntual contra el servicio real.

Uso: python -m scripts.manual_check_cima
"""

import asyncio
import sys

from src.infrastructure.external.cima_client import CimaAPIClient

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


async def main() -> None:
    async with CimaAPIClient() as client:
        resultados = await client.search_medicamentos("ibuprofeno")

        if not resultados:
            print("No se obtuvieron resultados.")
            return

        top3 = resultados[:3]
        print(
            f"Encontrados {len(resultados)} resultados para 'ibuprofeno'. Mostrando los 3 primeros:\n"
        )

        detalles: dict[str, dict | None] = {}
        for medicamento in top3:
            nregistro = medicamento["nregistro"]
            detalle = await client.get_medicamento_by_nregistro(nregistro)
            detalles[nregistro] = detalle
            cns = [
                presentacion.get("cn")
                for presentacion in (detalle or {}).get("presentaciones", [])
            ]

            print(f"Nombre: {medicamento.get('nombre')}")
            print(f"Nº de registro: {nregistro}")
            print(f"Laboratorio titular: {medicamento.get('labtitular')}")
            print(f"CN: {', '.join(cns) if cns else 'no disponible'}")
            print("-" * 40)

        primer_nregistro = top3[0]["nregistro"]
        print(f"\nDetalle completo del medicamento con nregistro={primer_nregistro}:\n")
        print(detalles[primer_nregistro])


if __name__ == "__main__":
    asyncio.run(main())
