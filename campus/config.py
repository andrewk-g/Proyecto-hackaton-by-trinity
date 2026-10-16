"""Carga y valida config/reglas.yaml (única fuente de verdad, principio P1)."""
from pathlib import Path

import yaml

RUTA_CONFIG = Path(__file__).resolve().parent.parent / "config" / "reglas.yaml"

_ultima_valida = None


class ConfigInvalida(Exception):
    pass


def _minutos(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def validar(cfg):
    """Devuelve la lista de errores de coherencia (vacía si todo está bien)."""
    errores = []
    h, r, lim, inc, ia = cfg["horario"], cfg["reservas"], cfg["limites"], cfg["incidencias"], cfg["ia"]
    g = h["granularidad_min"]
    jornada = _minutos(h["cierre"]) - _minutos(h["apertura"])

    if jornada <= 0:
        errores.append("horario: la hora de cierre debe ser posterior a la de apertura")
    for campo in ("duracion_min", "duracion_max"):
        if r[campo] % g:
            errores.append(f"reservas.{campo} ({r[campo]}) debe ser múltiplo de granularidad_min ({g})")
    if r["duracion_min"] > r["duracion_max"]:
        errores.append("reservas: duracion_min no puede superar duracion_max")
    if r["duracion_max"] > jornada:
        errores.append("reservas.duracion_max no cabe dentro del horario")
    if not 0 <= r["ocupacion_min_pct"] <= 100:
        errores.append("reservas.ocupacion_min_pct debe estar entre 0 y 100")
    if r["sala_grande_desde_aforo"] <= 0:
        errores.append("reservas.sala_grande_desde_aforo debe ser mayor que 0")

    if inc["prioridad_que_inhabilita"] not in inc["prioridades"]:
        errores.append("incidencias.prioridad_que_inhabilita no está en prioridades")
    for p in inc["prioridades_con_aviso"]:
        if p not in inc["prioridades"]:
            errores.append(f"incidencias.prioridades_con_aviso: '{p}' no está en prioridades")
    slas = [inc["sla_horas"].get(p) for p in inc["prioridades"]]
    if None in slas:
        errores.append("incidencias.sla_horas debe tener un valor por cada prioridad")
    elif slas != sorted(slas, reverse=True):
        errores.append("incidencias.sla_horas debe decrecer con la prioridad")

    if not 0 <= ia["umbral_confianza"] <= 1:
        errores.append("ia.umbral_confianza debe estar entre 0 y 1")

    impactos_validos = {"invalida", "degrada", "no_afecta"}
    for clave, el in cfg["elementos"].items():
        if el.get("impacto") not in impactos_validos:
            errores.append(f"elementos.{clave}: impacto inválido")
        if not el.get("area"):
            errores.append(f"elementos.{clave}: falta área responsable")
    for clave in cfg["elementos_base"]:
        if clave not in cfg["elementos"]:
            errores.append(f"elementos_base: '{clave}' no está definido en elementos")
    for nombre, esp in (cfg.get("espacios") or {}).items():
        for clave, imp in (esp.get("excepciones") or {}).items():
            if clave not in cfg["elementos"] or imp not in impactos_validos:
                errores.append(f"espacios.{nombre}: excepción inválida '{clave}: {imp}'")
        for clave in esp.get("elementos_extra") or []:
            if clave not in cfg["elementos"]:
                errores.append(f"espacios.{nombre}: elemento extra '{clave}' no definido")

    techo = lim["global"]["prestamos_activos_max_persona"]
    vistos = {}
    for clave, pool in cfg["pools"].items():
        if not pool.get("area"):
            errores.append(f"pools.{clave}: falta área responsable")
        for t in pool["tipos_dataset"]:
            t_norm = t.strip().lower()
            if t_norm in vistos:
                errores.append(f"El tipo '{t}' está en dos pools: {vistos[t_norm]} y {clave}")
            vistos[t_norm] = clave
        pl = pool.get("limites") or {}
        if pl.get("prestamos_activos_max_persona", 0) > techo:
            errores.append(f"pools.{clave}: su límite supera el techo global ({techo})")
        dur = pl.get("prestamo_duracion_max_min")
        if dur is not None and dur % g:
            errores.append(f"pools.{clave}: duración debe ser múltiplo de {g}")
    return errores


def cargar():
    """Lee y valida el YAML. Si es inválido, lanza ConfigInvalida."""
    global _ultima_valida
    with open(RUTA_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    errores = validar(cfg)
    if errores:
        raise ConfigInvalida(errores)
    _ultima_valida = cfg
    return cfg


def recargar():
    """Intenta recargar; si falla, conserva la última válida. Devuelve (cfg, errores)."""
    try:
        return cargar(), []
    except ConfigInvalida as e:
        return _ultima_valida, e.args[0]
    except Exception as e:  # YAML mal escrito
        return _ultima_valida, [f"No se pudo leer el archivo: {e}"]


def pool_de_tipo(cfg, tipo_dataset):
    t = (tipo_dataset or "").strip().lower()
    for clave, pool in cfg["pools"].items():
        if t in (x.strip().lower() for x in pool["tipos_dataset"]):
            return clave
    return None


def elementos_de_espacio(cfg, nombre_espacio):
    extra = ((cfg.get("espacios") or {}).get(nombre_espacio) or {}).get("elementos_extra") or []
    return list(cfg["elementos_base"]) + list(extra)


def impacto_elemento(cfg, nombre_espacio, elemento):
    exc = ((cfg.get("espacios") or {}).get(nombre_espacio) or {}).get("excepciones") or {}
    return exc.get(elemento, cfg["elementos"][elemento]["impacto"])
