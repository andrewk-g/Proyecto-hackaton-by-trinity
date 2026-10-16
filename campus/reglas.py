"""Reglas de negocio (R1–R9). Funciones puras: reciben datos y la configuración,
devuelven mensajes. Para cambiar un valor, editar config/reglas.yaml;
para cambiar una condición, editar la función de la regla correspondiente."""
from datetime import timedelta

from campus import fechas


def _min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ── R0: el intervalo de una reserva es coherente con el horario ──────────
def r0_intervalo(inicio, fin, cfg, ahora):
    h, r = cfg["horario"], cfg["reservas"]
    errores = []
    dur = (fin - inicio).total_seconds() / 60
    if fin <= inicio:
        return ["La hora de fin debe ser posterior a la de inicio."]
    if inicio < ahora - timedelta(minutes=h["granularidad_min"]):
        errores.append("No se puede reservar en el pasado.")
    if inicio > ahora + timedelta(days=r["anticipacion_max_dias"]):
        errores.append(f"Solo se puede reservar con hasta {r['anticipacion_max_dias']} días de anticipación.")
    if dur < r["duracion_min"] or dur > r["duracion_max"]:
        errores.append(f"La duración debe estar entre {r['duracion_min']} y {r['duracion_max']} minutos.")
    if dur % h["granularidad_min"] or inicio.minute % h["granularidad_min"]:
        errores.append(f"Las reservas van en bloques de {h['granularidad_min']} minutos.")
    if inicio.weekday() not in h["dias_habiles"]:
        errores.append("Ese día el campus no está abierto.")
    m_ini, m_fin = inicio.hour * 60 + inicio.minute, fin.hour * 60 + fin.minute
    if inicio.date() != fin.date() or m_ini < _min(h["apertura"]) or m_fin > _min(h["cierre"]):
        errores.append(f"La reserva debe estar dentro del horario {h['apertura']}–{h['cierre']}.")
    return errores


# ── R1: sin solapamiento en un mismo espacio ─────────────────────────────
def r1_solapamiento(inicio, fin, reservas_del_espacio, cfg):
    """Intervalos semiabiertos [inicio, fin) con margen opcional."""
    margen = timedelta(minutes=cfg["reservas"]["margen_entre_reservas_min"])
    for r in reservas_del_espacio:
        o_ini, o_fin = fechas.de_iso(r["inicio"]), fechas.de_iso(r["fin"])
        if inicio < o_fin + margen and o_ini < fin + margen:
            return [f"El espacio ya está reservado de {o_ini:%H:%M} a {o_fin:%H:%M} ({r['id']})."]
    return []


# ── R2: asistentes dentro del aforo ──────────────────────────────────────
def r2_aforo(asistentes, espacio, cfg):
    maximo = int(espacio["aforo"] * cfg["reservas"]["factor_aforo"])
    if asistentes < 1:
        return ["El número de asistentes debe ser al menos 1."]
    if asistentes > maximo:
        return [f"{espacio['nombre']} admite máximo {maximo} personas. Solicitaste {asistentes}."]
    return []


# ── R3: no se asigna nada inhabilitado ───────────────────────────────────
def r3_espacio_habilitado(espacio):
    if espacio["estado"] == "inhabilitado":
        return [f"{espacio['nombre']} está inhabilitado ({espacio['inhabilitacion']})."]
    return []


def r3_aviso_en_revision(incidencias_en_revision):
    """D1.6: con una incidencia crítica en revisión se permite, pero se advierte."""
    if incidencias_en_revision:
        return ["Hay una incidencia crítica en revisión para este espacio."]
    return []


# ── R4: límites de préstamo por persona (global o por pool) ──────────────
def r4_limite_prestamos(prestamos_activos, pool_clave, cfg, ahora):
    """prestamos_activos: lista de dicts con 'pool' y 'fin_esperado' de la persona."""
    lim = cfg["limites"]
    techo = lim["global"]["prestamos_activos_max_persona"]
    vencidos = [p for p in prestamos_activos if fechas.de_iso(p["fin_esperado"]) < ahora]
    if vencidos:
        return [f"Tienes un préstamo vencido ({vencidos[0]['recurso_id']}). Devuélvelo antes de pedir otro."]
    if lim["por_pool"]:
        pool_lim = (cfg["pools"][pool_clave].get("limites") or {}).get("prestamos_activos_max_persona", techo)
        del_pool = [p for p in prestamos_activos if p["pool"] == pool_clave]
        if len(del_pool) >= pool_lim:
            return [f"Límite del pool {cfg['pools'][pool_clave]['nombre']}: {pool_lim} préstamo(s) activo(s)."]
        if len(prestamos_activos) >= techo:
            return [f"Límite total por persona: {techo} préstamo(s) activo(s)."]
        return []
    if len(prestamos_activos) >= techo:
        return [f"Límite global: {techo} préstamo(s) activo(s) por persona."]
    return []


def duracion_max_prestamo(pool_clave, cfg):
    lim = cfg["limites"]
    glob = lim["global"]["prestamo_duracion_max_min"]
    if lim["por_pool"]:
        return (cfg["pools"][pool_clave].get("limites") or {}).get("prestamo_duracion_max_min", glob)
    return glob


# ── R5: máquina de estados de los recursos ───────────────────────────────
def r5_transicion(actual, nuevo, cfg):
    if nuevo not in cfg["transiciones_recurso"].get(actual, []):
        return [f"No se puede pasar un recurso de '{actual}' a '{nuevo}'."]
    return []


# ── R6: impacto de una incidencia según elemento y prioridad ─────────────
def r6_efecto(impacto, prioridad, cfg):
    """Devuelve 'inhabilitar', 'aviso' o 'ninguno'."""
    inc = cfg["incidencias"]
    if impacto == "no_afecta" or prioridad not in inc["prioridades_con_aviso"]:
        return "ninguno"
    if impacto == "invalida" and prioridad == inc["prioridad_que_inhabilita"]:
        return "inhabilitar"
    return "aviso"


def umbral_pcs(aforo, cfg):
    """PCs dañados a partir de los cuales el espacio se inhabilita (derivada)."""
    pct = cfg["elementos"]["pc"]["invalida_si_danados_mayor_a_pct"]
    return int(aforo * pct / 100) + 1


# ── R7: inhabilitación automática ────────────────────────────────────────
def r7_automatica(prioridad, confianza, tiene_vinculo, cfg):
    """Devuelve (aplicar_sola: bool, motivo)."""
    if prioridad != cfg["incidencias"]["prioridad_que_inhabilita"]:
        return False, "No es crítica"
    if confianza < cfg["ia"]["umbral_confianza"]:
        return False, f"Confianza {confianza:.2f} por debajo del umbral {cfg['ia']['umbral_confianza']}"
    if not tiene_vinculo:
        return False, "Quien reporta no tiene vínculo vigente con el espacio o recurso"
    return True, "Crítica, confianza suficiente y vínculo vigente"


def vinculo_reserva(reserva, cfg, ahora):
    """Durante la reserva o hasta N minutos después de su fin. Sin ventana previa."""
    if reserva["estado"] not in ("confirmada", "finalizada", "en_conflicto"):
        return False
    post = timedelta(minutes=cfg["incidencias"]["ventana_reporte_post_min"])
    return fechas.de_iso(reserva["inicio"]) <= ahora <= fechas.de_iso(reserva["fin"]) + post


# ── R8: ocupación mínima en salas grandes (solo advertencia) ─────────────
def r8_ocupacion_minima(asistentes, espacio, cfg):
    r = cfg["reservas"]
    if espacio["aforo"] < r["sala_grande_desde_aforo"]:
        return []
    minimo = -(-espacio["aforo"] * r["ocupacion_min_pct"] // 100)   # redondeo hacia arriba
    if asistentes < minimo:
        return [f"{espacio['nombre']} es una sala grande (mínimo sugerido: {minimo} personas)."]
    return []
