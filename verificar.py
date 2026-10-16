"""Verifica que la instalación está completa.
Ejecutar:  python verificar.py"""
import os
import sys
from pathlib import Path

OK, FALLA, AVISO = "  [OK]   ", "  [FALLA]", "  [AVISO]"
problemas = 0


def revisar(condicion, bien, mal, grave=True):
    global problemas
    if condicion:
        print(OK, bien)
    else:
        print(FALLA if grave else AVISO, mal)
        problemas += grave


print("Verificando instalación...\n")

revisar(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}",
        f"Python {sys.version.split()[0]}: se requiere 3.10 o superior")

faltan = []
for modulo in ("streamlit", "yaml", "requests"):
    try:
        __import__(modulo)
    except ImportError:
        faltan.append(modulo)
mensaje = f"Faltan dependencias ({', '.join(faltan)}): ejecute  pip install -r requirements.txt"
if os.name == "nt" and len(str(Path(sys.prefix))) > 100:
    mensaje += ("\n           La ruta del proyecto es muy larga para Windows: muévalo a una ruta corta "
                "(ej. C:\\proyectos\\), borre .venv y reinstale.")
revisar(not faltan, "Dependencias instaladas", mensaje)
if faltan:
    sys.exit(1)

from campus import RAIZ, config, ia  # noqa: E402

try:
    config.cargar()
    print(OK, "config/reglas.yaml es válida")
except config.ConfigInvalida as e:
    revisar(False, "", "config/reglas.yaml tiene errores:\n           - " + "\n           - ".join(e.args[0]))

datos = RAIZ / os.getenv("DATA_DIR", "data/ejemplo")
revisar((datos / "espacios.csv").exists(), f"Datos encontrados en {datos.relative_to(RAIZ)}",
        f"No se encontraron los CSV en {datos}")

revisar((RAIZ / ".env").exists(), "Archivo .env encontrado",
        "Sin archivo .env: se usan los valores por defecto (opcional; ver .env.example)", grave=False)

ok, msg = ia.estado()
revisar(ok, msg, msg + "\n           Instale Ollama (https://ollama.com), ábralo y ejecute:  ollama pull " + ia.MODELO,
        grave=False)

print("\n" + ("Todo listo. Ejecute:  streamlit run app.py" if not problemas
              else f"{problemas} problema(s) por resolver."))
sys.exit(1 if problemas else 0)
