"""Carga el archivo .env de la raíz del proyecto (si existe) antes que cualquier módulo.
Las variables ya definidas en el sistema tienen prioridad."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

_env = RAIZ / ".env"
if _env.exists():
    for linea in _env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())
