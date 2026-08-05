"""Test unitario básico: el módulo de presentación (panel Streamlit) debe poder
importarse sin errores. `app.py` solo ejecuta `main()` bajo `if __name__ ==
"__main__"`, por lo que importarlo no requiere un contexto de ejecución de Streamlit."""

from __future__ import annotations

import importlib


def test_presentation_app_imports_without_errors() -> None:
    module = importlib.import_module("src.presentation.app")

    assert hasattr(module, "main")
