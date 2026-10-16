"""Orquestación: aplica las reglas, llama a la IA y persiste. Todo cambio queda en auditoría."""
import json
from datetime import timedelta

from campus import config as conf
from campus import fechas, ia, reglas
from campus.db import auditar, fila, filas

ESTADOS_OCUPAN = ("confirmada", "pendiente", "en_conflicto")


# ═══ Consultas ═══════════════════════════════════════════════════════════
def reservas_que_ocupan(con, espacio_id, excluir_id=None):
    return [r for r in filas(con, f"SELECT * FROM reservas WHERE espacio_id = ? AND estado IN {ESTADOS_OCUPAN}", espacio_id)
            if r["id"] != excluir_id]


def criticas_en_revision(con, espacio_id):
    return filas(con, "SELECT * FROM incidencias WHERE espacio_id = ? AND estado = 'pendiente_verificacion' "
                      "AND prioridad = 'critica'", espacio_id)


def avisos_espacio(con, cfg, espacio):
    """Avisos visibles al reservar: elementos que degradan, PCs dañados y críticas en revisión."""
    avisos = []
    abiertas = filas(con, "SELECT * FROM incidencias WHERE espacio_id = ? AND estado IN ('abierta', 'aplicada')",
                     espacio["id"])
    for inc in abiertas:
        imp = conf.impacto_elemento(cfg, espacio["nombre"], inc["elemento"]) if inc["elemento"] in cfg["elementos"] else "no_afecta"
        if reglas.r6_efecto(imp, inc["prioridad"], cfg) == "aviso" and inc["elemento"] != "pc":
            avisos.append(f"{cfg['elementos'][inc['elemento']]['nombre']} con falla ({inc['prioridad']})")
    danados = fila(con, "SELECT COUNT(*) n FROM elementos WHERE espacio_id = ? AND tipo = 'pc' AND estado = 'danado'",
                   espacio["id"])["n"]
    if danados:
        avisos.append(f"{danados} PC(s) dañado(s) (se inhabilita con {reglas.umbral_pcs(espacio['aforo'], cfg)})")
    avisos += reglas.r3_aviso_en_revision(criticas_en_revision(con, espacio["id"]))
    return avisos


# ═══ Espacios ════════════════════════════════════════════════════════════
def crear_reserva(con, cfg, actor, persona_id, espacio_id, inicio, fin, asistentes, ahora=None):
    ahora = ahora or fechas.ahora()
    espacio = fila(con, "SELECT * FROM espacios WHERE id = ?", espacio_id)
    errores = reglas.r0_intervalo(inicio, fin, cfg, ahora)
    errores += reglas.r2_aforo(asistentes, espacio, cfg)
    errores += reglas.r3_espacio_habilitado(espacio)
    errores += reglas.r1_solapamiento(inicio, fin, reservas_que_ocupan(con, espacio_id), cfg)
    activas = fila(con, "SELECT COUNT(*) n FROM reservas WHERE persona_id = ? AND estado = 'confirmada' AND fin > ?",
                   persona_id, fechas.iso(ahora))["n"]
    if activas >= cfg["reservas"]["reservas_activas_max_persona"]:
        errores.append(f"Máximo {cfg['reservas']['reservas_activas_max_persona']} reservas activas por persona.")
    if errores:
        return {"ok": False, "errores": errores}
    avisos = reglas.r8_ocupacion_minima(asistentes, espacio, cfg) + avisos_espacio(con, cfg, espacio)
    nuevo_id = "B" + str(fila(con, "SELECT COUNT(*) n FROM reservas")["n"] + 1).zfill(3)
    con.execute("INSERT INTO reservas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (nuevo_id, espacio_id, persona_id, fechas.iso(inicio), fechas.iso(fin), asistentes,
                 None, "confirmada", "; ".join(avisos) or None))
    con.commit()
    auditar(con, actor, "reserva_creada", {"id": nuevo_id, "espacio": espacio["nombre"], "persona": persona_id,
                                           "inicio": inicio, "fin": fin, "asistentes": asistentes, "avisos": avisos})
    return {"ok": True, "id": nuevo_id, "avisos": avisos}


def candidatos(con, cfg, inicio, fin, asistentes, excluir_espacio=None, excluir_reserva=None):
    """Filtro de reglas + orden best-fit (aforo más ajustado)."""
    lista = []
    for e in filas(con, "SELECT * FROM espacios WHERE estado = 'disponible' ORDER BY aforo"):
        if e["id"] == excluir_espacio or reglas.r2_aforo(asistentes, e, cfg):
            continue
        if reglas.r1_solapamiento(inicio, fin, reservas_que_ocupan(con, e["id"], excluir_reserva), cfg):
            continue
        if criticas_en_revision(con, e["id"]):      # D1.6: las recomendaciones lo excluyen
            continue
        avisos = reglas.r8_ocupacion_minima(asistentes, e, cfg) + avisos_espacio(con, cfg, e)
        lista.append({**e, "avisos": "; ".join(avisos)})
    return lista


def recomendar(con, cfg, inicio, fin, asistentes, excluir_espacio=None, excluir_reserva=None, usar_ia=True):
    cands = candidatos(con, cfg, inicio, fin, asistentes, excluir_espacio, excluir_reserva)
    if not cands:
        return {"candidatos": [], "elegido": None, "explicacion": "No hay espacios que cumplan las reglas.", "origen": "reglas"}
    if usar_ia:
        datos, meta = ia.explicar_recomendacion(cfg, asistentes, inicio, fin, cands[:5])
        auditar(con, "ia", "recomendacion", {"asistentes": asistentes, "candidatos": [c["nombre"] for c in cands[:5]], **meta})
        if datos:
            elegido = next(c for c in cands if c["nombre"] == datos["espacio_elegido"])
            return {"candidatos": cands, "elegido": elegido, "explicacion": datos["explicacion"], "origen": "ia"}
    return {"candidatos": cands, "elegido": cands[0],
            "explicacion": "Recomendación por reglas (sin explicación IA): aforo más ajustado.", "origen": "reglas"}


def marcar_conflictos(con, espacio, actor, ahora):
    """D2: reservas futuras del espacio inhabilitado quedan en conflicto."""
    afectadas = filas(con, "SELECT * FROM reservas WHERE espacio_id = ? AND estado = 'confirmada' AND fin > ?",
                      espacio["id"], fechas.iso(ahora))
    for r in afectadas:
        con.execute("UPDATE reservas SET estado = 'en_conflicto', nota = ? WHERE id = ?",
                    (f"{espacio['nombre']} inhabilitado: requiere reasignación", r["id"]))
    con.commit()
    if afectadas:
        auditar(con, actor, "conflictos_marcados", {"espacio": espacio["nombre"], "reservas": [r["id"] for r in afectadas]})
    return len(afectadas)


def _restaurar_conflictos(con, espacio, actor):
    """Al rehabilitar: las no reasignadas vuelven a la normalidad."""
    afectadas = filas(con, "SELECT id FROM reservas WHERE espacio_id = ? AND estado = 'en_conflicto'", espacio["id"])
    con.execute("UPDATE reservas SET estado = 'confirmada', nota = 'Conflicto resuelto: espacio rehabilitado' "
                "WHERE espacio_id = ? AND estado = 'en_conflicto'", (espacio["id"],))
    con.commit()
    if afectadas:
        auditar(con, actor, "conflictos_resueltos", {"espacio": espacio["nombre"], "reservas": [r["id"] for r in afectadas]})


def inhabilitar_espacio(con, espacio_id, tipo, actor, ahora=None):
    ahora = ahora or fechas.ahora()
    con.execute("UPDATE espacios SET estado = 'inhabilitado', inhabilitacion = ? WHERE id = ?", (tipo, espacio_id))
    con.commit()
    espacio = fila(con, "SELECT * FROM espacios WHERE id = ?", espacio_id)
    auditar(con, actor, "espacio_inhabilitado", {"espacio": espacio["nombre"], "tipo": tipo})
    return marcar_conflictos(con, espacio, actor, ahora)


def rehabilitar_espacio(con, espacio_id, actor):
    """D3: manual (TI) para inhabilitación directa."""
    espacio = fila(con, "SELECT * FROM espacios WHERE id = ?", espacio_id)
    con.execute("UPDATE espacios SET estado = 'disponible', inhabilitacion = NULL WHERE id = ?", (espacio_id,))
    con.execute("UPDATE elementos SET estado = 'operativo' WHERE espacio_id = ? AND tipo != 'pc'", (espacio_id,))
    con.execute("UPDATE incidencias SET estado = 'resuelta' WHERE espacio_id = ? AND estado = 'aplicada' "
                "AND elemento != 'pc'", (espacio_id,))
    con.commit()
    auditar(con, actor, "espacio_rehabilitado", {"espacio": espacio["nombre"]})
    _restaurar_conflictos(con, espacio, actor)


def recalcular_derivada(con, cfg, espacio_id, actor, ahora=None):
    """Inhabilitación derivada por PCs: se calcula y se rehabilita sola."""
    espacio = fila(con, "SELECT * FROM espacios WHERE id = ?", espacio_id)
    danados = fila(con, "SELECT COUNT(*) n FROM elementos WHERE espacio_id = ? AND tipo = 'pc' AND estado = 'danado'",
                   espacio_id)["n"]
    umbral = reglas.umbral_pcs(espacio["aforo"], cfg)
    if danados >= umbral and espacio["estado"] == "disponible":
        inhabilitar_espacio(con, espacio_id, "derivada", actor, ahora)
    elif danados < umbral and espacio["inhabilitacion"] == "derivada":
        con.execute("UPDATE espacios SET estado = 'disponible', inhabilitacion = NULL WHERE id = ?", (espacio_id,))
        con.commit()
        auditar(con, actor, "espacio_rehabilitado_auto", {"espacio": espacio["nombre"], "pcs_danados": danados})
        _restaurar_conflictos(con, espacio, actor)
    return danados, umbral


def reparar_pc(con, cfg, pc_id, actor):
    pc = fila(con, "SELECT * FROM elementos WHERE id = ?", pc_id)
    con.execute("UPDATE elementos SET estado = 'operativo' WHERE id = ?", (pc_id,))
    con.commit()
    auditar(con, actor, "pc_reparado", {"pc": pc_id})
    return recalcular_derivada(con, cfg, pc["espacio_id"], actor)


def reasignar(con, cfg, reserva_id, nuevo_espacio_id, actor):
    r = fila(con, "SELECT * FROM reservas WHERE id = ?", reserva_id)
    esp = fila(con, "SELECT * FROM espacios WHERE id = ?", nuevo_espacio_id)
    ini, fin = fechas.de_iso(r["inicio"]), fechas.de_iso(r["fin"])
    errores = reglas.r3_espacio_habilitado(esp)
    if r["asistentes"] is None:
        errores.append("La reserva no tiene número de asistentes: complételo antes de reasignar.")
    else:
        errores += reglas.r2_aforo(r["asistentes"], esp, cfg)
    errores += reglas.r1_solapamiento(ini, fin, reservas_que_ocupan(con, nuevo_espacio_id, reserva_id), cfg)
    if errores:
        return {"ok": False, "errores": errores}
    origen = fila(con, "SELECT nombre FROM espacios WHERE id = ?", r["espacio_id"])["nombre"]
    con.execute("UPDATE reservas SET espacio_id = ?, estado = 'confirmada', nota = ? WHERE id = ?",
                (nuevo_espacio_id, f"Reasignada desde {origen}", reserva_id))
    con.commit()
    auditar(con, actor, "reserva_reasignada", {"reserva": reserva_id, "desde": origen, "hacia": esp["nombre"]})
    return {"ok": True}


# ═══ Recursos ════════════════════════════════════════════════════════════
def prestamos_activos(con, persona_id):
    return filas(con, "SELECT p.*, r.pool FROM prestamos p JOIN recursos r ON r.id = p.recurso_id "
                      "WHERE p.persona_id = ? AND p.devolucion_real IS NULL", persona_id)


def prestar(con, cfg, actor, persona_id, recurso_id, fin_esperado, ahora=None):
    ahora = ahora or fechas.ahora()
    if fila(con, "SELECT id FROM elementos WHERE id = ?", recurso_id):      # R9
        return {"ok": False, "errores": [f"{recurso_id} está instalado en un espacio y no se presta."]}
    rec = fila(con, "SELECT * FROM recursos WHERE id = ?", recurso_id)
    errores = reglas.r5_transicion(rec["estado"], "prestado", cfg)
    errores += reglas.r4_limite_prestamos(prestamos_activos(con, persona_id), rec["pool"], cfg, ahora)
    dur_max = reglas.duracion_max_prestamo(rec["pool"], cfg)
    if fin_esperado <= ahora:
        errores.append("La devolución debe ser posterior a ahora.")
    elif (fin_esperado - ahora).total_seconds() / 60 > dur_max:
        errores.append(f"Duración máxima para este recurso: {dur_max} minutos.")
    cierre = reglas._min(cfg["horario"]["cierre"])
    if fin_esperado.date() != ahora.date() or fin_esperado.hour * 60 + fin_esperado.minute > cierre:
        errores.append(f"El préstamo debe devolverse hoy antes del cierre ({cfg['horario']['cierre']}).")
    if errores:
        return {"ok": False, "errores": errores}
    nuevo_id = "L" + str(fila(con, "SELECT COUNT(*) n FROM prestamos")["n"] + 1).zfill(3)
    con.execute("INSERT INTO prestamos VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (nuevo_id, recurso_id, persona_id, fechas.iso(ahora), fechas.iso(fin_esperado)))
    con.execute("UPDATE recursos SET estado = 'prestado' WHERE id = ?", (recurso_id,))
    con.commit()
    auditar(con, actor, "prestamo_creado", {"id": nuevo_id, "recurso": recurso_id, "persona": persona_id})
    return {"ok": True, "id": nuevo_id}


def devolver(con, cfg, actor, prestamo_id, danado=False, ahora=None):
    ahora = ahora or fechas.ahora()
    p = fila(con, "SELECT * FROM prestamos WHERE id = ?", prestamo_id)
    rec = fila(con, "SELECT * FROM recursos WHERE id = ?", p["recurso_id"])
    con.execute("UPDATE prestamos SET devolucion_real = ?, observacion = ? WHERE id = ?",
                (fechas.iso(ahora), "dañado" if danado else "sin observaciones", prestamo_id))
    nuevo = "danado" if danado or rec["estado"] == "danado" else "disponible"
    if rec["estado"] == "prestado":
        con.execute("UPDATE recursos SET estado = ? WHERE id = ?", (nuevo, rec["id"]))
    con.commit()
    auditar(con, actor, "prestamo_devuelto", {"prestamo": prestamo_id, "recurso": rec["id"], "estado_recurso": nuevo})
    return {"ok": True, "estado": nuevo}


def cambiar_estado_recurso(con, cfg, actor, recurso_id, nuevo):
    rec = fila(con, "SELECT * FROM recursos WHERE id = ?", recurso_id)
    errores = reglas.r5_transicion(rec["estado"], nuevo, cfg)
    if errores:
        return {"ok": False, "errores": errores}
    con.execute("UPDATE recursos SET estado = ? WHERE id = ?", (nuevo, recurso_id))
    con.commit()
    auditar(con, actor, "recurso_estado", {"recurso": recurso_id, "de": rec["estado"], "a": nuevo})
    return {"ok": True}


# ═══ Incidencias ═════════════════════════════════════════════════════════
def contexto_incidencia(con, cfg, espacio_id=None, recurso_id=None):
    """Elementos e IDs válidos para el enum dinámico de la IA."""
    if espacio_id:
        esp = fila(con, "SELECT * FROM espacios WHERE id = ?", espacio_id)
        pcs = [e["id"] for e in filas(con, "SELECT id FROM elementos WHERE espacio_id = ? AND tipo = 'pc'", espacio_id)]
        return esp["nombre"], conf.elementos_de_espacio(cfg, esp["nombre"]), pcs
    rec = fila(con, "SELECT * FROM recursos WHERE id = ?", recurso_id)
    return f"Recurso {rec['nombre']}", [rec["pool"]], [recurso_id]


def tiene_vinculo(con, cfg, persona_id, espacio_id=None, recurso_id=None, ahora=None):
    ahora = ahora or fechas.ahora()
    if espacio_id:
        return any(reglas.vinculo_reserva(r, cfg, ahora) for r in
                   filas(con, "SELECT * FROM reservas WHERE persona_id = ? AND espacio_id = ?", persona_id, espacio_id))
    return fila(con, "SELECT id FROM prestamos WHERE persona_id = ? AND recurso_id = ? AND devolucion_real IS NULL",
                persona_id, recurso_id) is not None


def _efecto(con, cfg, inc):
    if inc["recurso_id"]:
        return "inhabilitar" if inc["prioridad"] == cfg["incidencias"]["prioridad_que_inhabilita"] else "ninguno"
    esp = fila(con, "SELECT * FROM espacios WHERE id = ?", inc["espacio_id"])
    if inc["elemento"] == "pc":
        return "inhabilitar" if inc["prioridad"] == cfg["incidencias"]["prioridad_que_inhabilita"] else "aviso"
    return reglas.r6_efecto(conf.impacto_elemento(cfg, esp["nombre"], inc["elemento"]), inc["prioridad"], cfg)


def area_de(con, cfg, espacio_id, recurso_id, elemento):
    if recurso_id:
        return cfg["pools"].get(elemento, {}).get("area", "TI")
    return cfg["elementos"][elemento]["area"]


def reportar(con, cfg, persona_id, texto, espacio_id=None, recurso_id=None, elemento_sel=None, ids_sel=None, ahora=None):
    """Flujo vertical: IA → validación → R7 → aplicar o verificación humana."""
    ahora = ahora or fechas.ahora()
    ids_sel = ids_sel or []
    nombre, elementos_validos, ids_validos = contexto_incidencia(con, cfg, espacio_id, recurso_id)
    datos, meta = ia.triaje(cfg, texto, nombre, elementos_validos, ids_sel, ids_validos)
    if not datos:
        auditar(con, "ia", "triaje_fallido", {"persona": persona_id, "texto": texto, **meta})
        return {"ok": False, "ia_fallo": True, "meta": meta}

    motivos = []
    if recurso_id:
        elemento_sel = elementos_validos[0]
    if elemento_sel and datos["elemento"] != elemento_sel:
        motivos.append(f"La IA identificó '{datos['elemento']}' pero se seleccionó '{elemento_sel}'")
    if set(datos["ids_afectados"]) != set(ids_sel) and (ids_sel or datos["elemento"] == "pc"):
        motivos.append("Los IDs que identificó la IA no coinciden con los seleccionados")
    vinculo = tiene_vinculo(con, cfg, persona_id, espacio_id, recurso_id, ahora)
    inc = {"espacio_id": espacio_id, "recurso_id": recurso_id, "elemento": datos["elemento"],
           "prioridad": datos["prioridad"]}
    efecto = _efecto(con, cfg, inc)
    automatica, motivo_r7 = reglas.r7_automatica(datos["prioridad"], datos["confianza"], vinculo, cfg)

    if efecto == "inhabilitar" and automatica and not motivos:
        estado, motivo = "aplicada", motivo_r7
    elif efecto == "inhabilitar" or motivos:
        estado, motivo = "pendiente_verificacion", "; ".join(motivos + ([] if automatica else [motivo_r7]))
    else:
        estado, motivo = "abierta", f"Efecto: {efecto}"

    cur = con.execute(
        "INSERT INTO incidencias (creada, persona_id, espacio_id, recurso_id, elemento, ids_afectados, texto, "
        "prioridad, confianza, resumen, justificacion, area, origen, estado, motivo) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ia', ?, ?)",
        (fechas.iso(ahora), persona_id, espacio_id, recurso_id, datos["elemento"],
         json.dumps(datos["ids_afectados"] or ids_sel), texto, datos["prioridad"], datos["confianza"],
         datos["resumen"], datos["justificacion"], area_de(con, cfg, espacio_id, recurso_id, datos["elemento"]),
         estado, motivo))
    con.commit()
    inc_id = cur.lastrowid
    auditar(con, "ia", "triaje", {"incidencia": inc_id, "persona": persona_id, "resultado": datos,
                                   "vinculo": vinculo, "efecto": efecto, "estado": estado, "motivo": motivo, **meta})
    detalle = None
    if estado == "aplicada":
        detalle = aplicar(con, cfg, inc_id, "sistema (R7)", ahora)
    return {"ok": True, "id": inc_id, "datos": datos, "estado": estado, "motivo": motivo,
            "efecto": efecto, "vinculo": vinculo, "detalle": detalle}


def reportar_manual(con, cfg, persona_id, texto, elemento, prioridad, espacio_id=None, recurso_id=None, ids=None):
    """Si la IA no está disponible: se registra sin IA y va a verificación humana."""
    cur = con.execute(
        "INSERT INTO incidencias (creada, persona_id, espacio_id, recurso_id, elemento, ids_afectados, texto, "
        "prioridad, confianza, resumen, justificacion, area, origen, estado, motivo) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, 'manual', 'pendiente_verificacion', ?)",
        (fechas.iso(fechas.ahora()), persona_id, espacio_id, recurso_id, elemento, json.dumps(ids or []), texto,
         prioridad, texto[:120], area_de(con, cfg, espacio_id, recurso_id, elemento), "Clasificación manual (IA no disponible)"))
    con.commit()
    auditar(con, persona_id, "incidencia_manual", {"incidencia": cur.lastrowid, "elemento": elemento, "prioridad": prioridad})
    return cur.lastrowid


def aplicar(con, cfg, inc_id, actor, ahora=None):
    """Aplica las consecuencias de una incidencia (automática o confirmada)."""
    inc = fila(con, "SELECT * FROM incidencias WHERE id = ?", inc_id)
    efecto = _efecto(con, cfg, inc)
    con.execute("UPDATE incidencias SET estado = 'aplicada' WHERE id = ?", (inc_id,))
    con.commit()
    if inc["recurso_id"]:
        rec = fila(con, "SELECT * FROM recursos WHERE id = ?", inc["recurso_id"])
        if efecto == "inhabilitar" and not reglas.r5_transicion(rec["estado"], "danado", cfg):
            con.execute("UPDATE recursos SET estado = 'danado' WHERE id = ?", (rec["id"],))
            con.commit()
            auditar(con, actor, "recurso_danado", {"recurso": rec["id"], "incidencia": inc_id})
            return f"{rec['nombre']} pasó a dañado."
        return "Sin cambio de estado del recurso."
    if inc["elemento"] == "pc" and efecto == "inhabilitar":
        for pc in json.loads(inc["ids_afectados"] or "[]"):
            con.execute("UPDATE elementos SET estado = 'danado' WHERE id = ?", (pc,))
        con.commit()
        danados, umbral = recalcular_derivada(con, cfg, inc["espacio_id"], actor, ahora)
        return f"PCs dañados en el espacio: {danados} (umbral de inhabilitación: {umbral})."
    if efecto == "inhabilitar":
        con.execute("UPDATE elementos SET estado = 'danado' WHERE espacio_id = ? AND tipo = ?",
                    (inc["espacio_id"], inc["elemento"]))
        n = inhabilitar_espacio(con, inc["espacio_id"], "directa", actor, ahora)
        return f"Espacio inhabilitado. Reservas en conflicto: {n}."
    return "Aviso visible en las reservas del espacio." if efecto == "aviso" else "Sin efecto en el espacio."


def verificar(con, cfg, inc_id, accion, actor, nueva_prioridad=None):
    """5a: confirmar, reclasificar o descartar. 5b: descartar una aplicada la revierte."""
    inc = fila(con, "SELECT * FROM incidencias WHERE id = ?", inc_id)
    if accion == "reclasificar":
        con.execute("UPDATE incidencias SET prioridad = ? WHERE id = ?", (nueva_prioridad, inc_id))
        con.commit()
        auditar(con, actor, "incidencia_reclasificada", {"incidencia": inc_id, "de": inc["prioridad"], "a": nueva_prioridad})
        return "Prioridad actualizada; ahora confirme o descarte."
    if accion == "confirmar":
        auditar(con, actor, "incidencia_confirmada", {"incidencia": inc_id})
        return aplicar(con, cfg, inc_id, actor)
    # descartar
    con.execute("UPDATE incidencias SET estado = 'descartada' WHERE id = ?", (inc_id,))
    con.commit()
    auditar(con, actor, "incidencia_descartada", {"incidencia": inc_id, "estado_previo": inc["estado"]})
    if inc["estado"] == "aplicada" and inc["espacio_id"]:
        if inc["elemento"] == "pc":
            for pc in json.loads(inc["ids_afectados"] or "[]"):
                con.execute("UPDATE elementos SET estado = 'operativo' WHERE id = ?", (pc,))
            con.commit()
            recalcular_derivada(con, cfg, inc["espacio_id"], actor)
        elif fila(con, "SELECT inhabilitacion FROM espacios WHERE id = ?", inc["espacio_id"])["inhabilitacion"] == "directa":
            rehabilitar_espacio(con, inc["espacio_id"], actor)
        return "Incidencia descartada y efecto revertido."
    return "Incidencia descartada."


def resolver(con, inc_id, actor):
    con.execute("UPDATE incidencias SET estado = 'resuelta' WHERE id = ?", (inc_id,))
    con.commit()
    auditar(con, actor, "incidencia_resuelta", {"incidencia": inc_id})
