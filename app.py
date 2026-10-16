"""Interfaz del Sistema Central de Gestión Operativa (Streamlit).
Ejecutar:  streamlit run app.py"""
import json
import os
from datetime import datetime, time, timedelta

import streamlit as st

from campus import config as conf
from campus import db, fechas, ia, importador
from campus import servicios as s

st.set_page_config(page_title="Campus · Gestión Operativa", page_icon="🏫", layout="wide")

DATA_DIR = os.getenv("DATA_DIR", "data/ejemplo")
ETIQUETA_ROL = {"usuario": "Usuario", "administrativo": "Administrativo", "ti": "TI"}
COLOR_ESTADO = {"aplicada": "🔴", "pendiente_verificacion": "🟠", "abierta": "🟡", "descartada": "⚪", "resuelta": "🟢"}


# ─── Estado de la sesión ─────────────────────────────────────────────────
def iniciar():
    if "cfg" not in st.session_state:
        st.session_state.cfg, errores = conf.recargar()
        if errores:
            st.error("La configuración tiene errores:\n\n- " + "\n- ".join(errores))
            st.stop()
    if "con" not in st.session_state:
        con = db.conectar()
        if not db.fila(con, "SELECT COUNT(*) n FROM personas")["n"]:
            importador.importar(con, st.session_state.cfg, DATA_DIR)
        st.session_state.con = con
    if "ia_lista" not in st.session_state:
        ok, msg = ia.estado()
        if ok:
            with st.spinner("Cargando el modelo de IA en la GPU (solo la primera vez)…"):
                ia.precalentar(st.session_state.cfg)
        st.session_state.ia_lista, st.session_state.ia_msg = ok, msg


def avisar(tipo, texto):
    st.session_state.setdefault("flash", []).append((tipo, texto))


def mostrar_flash():
    for tipo, texto in st.session_state.pop("flash", []):
        getattr(st, tipo)(texto)


def mostrar_resultado(res, exito):
    if res.get("ok"):
        avisar("success", exito)
        for a in res.get("avisos") or []:
            avisar("warning", a)
    else:
        for e in res["errores"]:
            avisar("error", e)


iniciar()
cfg, con = st.session_state.cfg, st.session_state.con
ahora = fechas.ahora()

# ─── Barra lateral ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏫 Campus")
    personas = db.filas(con, "SELECT * FROM personas ORDER BY rol DESC, nombre")
    etiquetas = {p["id"]: f"{p['nombre']} · {p['rol_dataset']}" for p in personas}
    pid = st.selectbox("Actuando como", list(etiquetas), format_func=etiquetas.get)
    persona = next(p for p in personas if p["id"] == pid)
    rol = persona["rol"]
    st.caption(f"Rol: **{ETIQUETA_ROL[rol]}** · {ahora:%A %d/%m %H:%M}")
    (st.success if st.session_state.ia_lista else st.error)(st.session_state.ia_msg)
    if not st.session_state.ia_lista and st.button("Reintentar conexión IA"):
        st.session_state.pop("ia_lista")
        st.rerun()
    if rol in ("administrativo", "ti"):
        st.divider()
        if st.button("🔄 Recargar configuración", width="stretch"):
            nuevo, errores = conf.recargar()
            if errores:
                avisar("error", "Configuración inválida, se conserva la anterior:\n\n- " + "\n- ".join(errores))
            else:
                st.session_state.cfg = nuevo
                db.auditar(con, pid, "config_recargada", {})
                avisar("success", "Configuración recargada y validada.")
            st.rerun()
        if st.button("♻️ Reimportar datos", width="stretch",
                     help="Reinicia la base y vuelve a importar los CSV (reprocesa la cuarentena)."):
            st.session_state.con = db.reiniciar()
            importador.importar(st.session_state.con, cfg, DATA_DIR, pid)
            avisar("success", "Datos reimportados.")
            st.rerun()

st.title("Sistema Central de Gestión Operativa")
mostrar_flash()

pestanas = []
if rol != "ti":
    pestanas += ["Espacios", "Préstamos"]
pestanas += ["Reportar incidencia", "Estado del campus"]
if rol in ("administrativo", "ti"):
    pestanas += ["Operación", "Datos y auditoría"]
tabs = dict(zip(pestanas, st.tabs(pestanas)))

espacios = db.filas(con, "SELECT * FROM espacios ORDER BY nombre")
nombre_esp = {e["id"]: e["nombre"] for e in espacios}


# ═══ Espacios ════════════════════════════════════════════════════════════
if "Espacios" in tabs:
    with tabs["Espacios"]:
        st.subheader("Reservar un espacio")
        g = cfg["horario"]["granularidad_min"]
        c1, c2, c3 = st.columns(3)
        with c1:
            if rol == "administrativo":
                para = st.selectbox("Reserva para", list(etiquetas), format_func=etiquetas.get, key="res_para")
            else:
                para = pid
            esp_id = st.selectbox("Espacio", [e["id"] for e in espacios],
                                  format_func=lambda i: next(f"{e['nombre']} (aforo {e['aforo']})"
                                                             + (" ⛔" if e["estado"] == "inhabilitado" else "")
                                                             for e in espacios if e["id"] == i))
        with c2:
            dia = st.date_input("Día", ahora.date(), min_value=ahora.date())
            apertura = datetime.strptime(cfg["horario"]["apertura"], "%H:%M")
            cierre = datetime.strptime(cfg["horario"]["cierre"], "%H:%M")
            slots = [(apertura + timedelta(minutes=m)).time()
                     for m in range(0, int((cierre - apertura).total_seconds() // 60), g)]
            hora = st.selectbox("Hora de inicio", slots, format_func=lambda t: t.strftime("%H:%M"),
                                index=next((i for i, t in enumerate(slots) if t >= ahora.time()), 0))
        with c3:
            duraciones = list(range(cfg["reservas"]["duracion_min"], cfg["reservas"]["duracion_max"] + 1, g))
            dur = st.selectbox("Duración (min)", duraciones, index=min(3, len(duraciones) - 1))
            asist = st.number_input("Asistentes (incluyéndote)", min_value=0, value=10, step=1)
        inicio = datetime.combine(dia, hora)
        fin = inicio + timedelta(minutes=dur)
        b1, b2 = st.columns(2)
        if b1.button("Reservar", type="primary", width="stretch"):
            res = s.crear_reserva(con, cfg, pid, para, esp_id, inicio, fin, int(asist), ahora)
            mostrar_resultado(res, f"Reserva {res.get('id')} confirmada en {nombre_esp[esp_id]}.")
            st.rerun()
        if b2.button("✨ Recomendar espacio", width="stretch"):
            with st.spinner("Buscando con reglas y explicando con IA…"):
                rec = s.recomendar(con, cfg, inicio, fin, int(asist), usar_ia=st.session_state.ia_lista)
            if rec["elegido"]:
                st.info(f"**Recomendado: {rec['elegido']['nombre']}** (aforo {rec['elegido']['aforo']})\n\n"
                        f"{'🤖' if rec['origen'] == 'ia' else '📏'} {rec['explicacion']}")
                st.dataframe([{"Espacio": c["nombre"], "Aforo": c["aforo"], "Avisos": c["avisos"]}
                              for c in rec["candidatos"]], hide_index=True)
            else:
                st.warning(rec["explicacion"])

        st.subheader("Reservas del día")
        del_dia = db.filas(con, "SELECT r.*, e.nombre espacio, p.nombre persona FROM reservas r "
                                "JOIN espacios e ON e.id = r.espacio_id JOIN personas p ON p.id = r.persona_id "
                                "WHERE substr(r.inicio, 1, 10) = ? ORDER BY r.inicio", dia.isoformat())
        st.dataframe([{"ID": r["id"], "Espacio": r["espacio"], "Inicio": r["inicio"][11:], "Fin": r["fin"][11:],
                       "Asistentes": r["asistentes"], "Persona": r["persona"], "Estado": r["estado"], "Nota": r["nota"]}
                      for r in del_dia], hide_index=True, width="stretch")


# ═══ Préstamos ═══════════════════════════════════════════════════════════
if "Préstamos" in tabs:
    with tabs["Préstamos"]:
        st.subheader("Pedir un préstamo")
        recursos = db.filas(con, "SELECT * FROM recursos ORDER BY pool, nombre")
        modo = "por pool" if cfg["limites"]["por_pool"] else "global"
        st.caption(f"Límites en modo **{modo}** (configurable con `limites.por_pool`).")
        c1, c2 = st.columns(2)
        rid = c1.selectbox("Recurso", [r["id"] for r in recursos],
                           format_func=lambda i: next(f"{r['nombre']} · {cfg['pools'][r['pool']]['nombre']} · {r['estado']}"
                                                      for r in recursos if r["id"] == i))
        hora_dev = c2.time_input("Devolver hoy a las", (ahora + timedelta(hours=2)).time().replace(second=0, microsecond=0))
        if st.button("Prestar", type="primary"):
            res = s.prestar(con, cfg, pid, pid, rid, datetime.combine(ahora.date(), hora_dev), ahora)
            mostrar_resultado(res, f"Préstamo {res.get('id')} registrado.")
            st.rerun()

        st.subheader("Mis préstamos activos")
        activos = s.prestamos_activos(con, pid)
        if not activos:
            st.caption("No tienes préstamos activos.")
        for p in activos:
            vencido = fechas.de_iso(p["fin_esperado"]) < ahora
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"**{p['recurso_id']}** · devolver {p['fin_esperado'].replace('T', ' ')}"
                     + (" · ⚠️ **vencido**" if vencido else ""))
            danado = c2.checkbox("Dañado", key=f"dan_{p['id']}")
            if c3.button("Devolver", key=f"dev_{p['id']}"):
                r = s.devolver(con, cfg, pid, p["id"], danado)
                avisar("success", f"Devuelto. Estado del recurso: {r['estado']}.")
                st.rerun()


# ═══ Reportar incidencia ═════════════════════════════════════════════════
with tabs["Reportar incidencia"]:
    st.subheader("Reportar una incidencia")
    sobre = st.radio("¿Sobre qué?", ["Un espacio", "Un recurso portátil"], horizontal=True)
    espacio_id = recurso_id = None
    ids_sel = []
    if sobre == "Un espacio":
        vigente = next((r for r in db.filas(con, "SELECT * FROM reservas WHERE persona_id = ?", pid)
                        if fechas.de_iso(r["inicio"]) <= ahora <= fechas.de_iso(r["fin"])), None)
        ids_esp = [e["id"] for e in espacios]
        indice = ids_esp.index(vigente["espacio_id"]) if vigente else 0
        c1, c2 = st.columns(2)
        espacio_id = c1.selectbox("Espacio", ids_esp, index=indice, format_func=nombre_esp.get,
                                  help="Se sugiere el espacio de tu reserva vigente.")
        elementos = conf.elementos_de_espacio(cfg, nombre_esp[espacio_id])
        elemento = c2.selectbox("Elemento", elementos, format_func=lambda k: cfg["elementos"][k]["nombre"])
        if elemento == "pc":
            pcs = [e["id"] for e in db.filas(con, "SELECT id FROM elementos WHERE espacio_id = ? AND tipo = 'pc' "
                                                  "AND estado = 'operativo'", espacio_id)]
            ids_sel = st.multiselect("¿Qué PCs?", pcs)
    else:
        mis = [p["recurso_id"] for p in s.prestamos_activos(con, pid)]
        todos = [r["id"] for r in db.filas(con, "SELECT id FROM recursos ORDER BY id")]
        recurso_id = st.selectbox("Recurso", todos, index=todos.index(mis[0]) if mis else 0,
                                  help="Se sugiere el recurso que tienes prestado.")
        elemento = None
    texto = st.text_area("Describe lo que pasa", placeholder="Ej: No hay internet en toda la sala")

    if st.button("🤖 Analizar y reportar", type="primary", disabled=not texto.strip()):
        if not st.session_state.ia_lista:
            st.session_state.manual = True
        else:
            with st.spinner("La IA está clasificando el reporte…"):
                res = s.reportar(con, cfg, pid, texto, espacio_id, recurso_id, elemento, ids_sel, ahora)
            if res.get("ia_fallo"):
                st.session_state.manual = True
            else:
                st.session_state.ultimo_reporte = res
                st.session_state.manual = False
        st.rerun()

    res = st.session_state.get("ultimo_reporte")
    if res and not st.session_state.get("manual"):
        d = res["datos"]
        st.markdown(f"**Clasificación IA:** {cfg['elementos'].get(d['elemento'], {}).get('nombre', d['elemento'])} · "
                    f"prioridad **{d['prioridad']}** · confianza {d['confianza']:.2f}")
        st.caption(f"{d['resumen']} — {d['justificacion']}")
        if res["estado"] == "aplicada":
            st.error(f"⛔ Aplicada automáticamente (R7). {res['detalle']}")
        elif res["estado"] == "pendiente_verificacion":
            st.warning(f"🟠 Enviada a verificación humana: {res['motivo']}")
        else:
            st.info(f"🟡 Incidencia registrada y enrutada. {res['motivo']}")
    if st.session_state.get("manual"):
        st.error("IA no disponible. Clasifique manualmente: la incidencia irá a verificación humana.")
        c1, c2 = st.columns(2)
        el_m = c1.selectbox("Elemento", conf.elementos_de_espacio(cfg, nombre_esp[espacio_id]) if espacio_id
                            else [db.fila(con, "SELECT pool FROM recursos WHERE id = ?", recurso_id)["pool"]],
                            key="el_manual")
        pr_m = c2.selectbox("Prioridad", cfg["incidencias"]["prioridades"], key="pr_manual")
        if st.button("Registrar manualmente"):
            nid = s.reportar_manual(con, cfg, pid, texto, el_m, pr_m, espacio_id, recurso_id, ids_sel)
            st.session_state.manual = False
            avisar("success", f"Incidencia #{nid} registrada para verificación humana.")
            st.rerun()


# ═══ Estado del campus ═══════════════════════════════════════════════════
with tabs["Estado del campus"]:
    st.subheader("Espacios")
    st.dataframe([{"Espacio": e["nombre"], "Aforo": e["aforo"],
                   "Estado": ("⛔ inhabilitado (" + e["inhabilitacion"] + ")") if e["estado"] == "inhabilitado" else "✅ disponible",
                   "Avisos": "; ".join(s.avisos_espacio(con, cfg, e))} for e in espacios],
                 hide_index=True, width="stretch")
    st.subheader("Recursos")
    st.dataframe([{"ID": r["id"], "Recurso": r["nombre"], "Pool": cfg["pools"][r["pool"]]["nombre"], "Estado": r["estado"]}
                  for r in db.filas(con, "SELECT * FROM recursos ORDER BY id")], hide_index=True, width="stretch")
    st.subheader("Incidencias")
    st.dataframe([{"#": i["id"], "": COLOR_ESTADO.get(i["estado"], ""), "Estado": i["estado"],
                   "Lugar": nombre_esp.get(i["espacio_id"]) or i["recurso_id"], "Elemento": i["elemento"],
                   "Prioridad": i["prioridad"], "Área": i["area"], "Resumen": i["resumen"]}
                  for i in db.filas(con, "SELECT * FROM incidencias ORDER BY id DESC")],
                 hide_index=True, width="stretch")


# ═══ Operación (Administrativo / TI) ═════════════════════════════════════
if "Operación" in tabs:
    with tabs["Operación"]:
        area = "Administrativo" if rol == "administrativo" else "TI"
        st.subheader(f"Verificación humana · área {area}")
        cola = db.filas(con, "SELECT * FROM incidencias WHERE area = ? AND estado IN ('pendiente_verificacion', 'aplicada', 'abierta') "
                             "ORDER BY CASE estado WHEN 'pendiente_verificacion' THEN 0 WHEN 'aplicada' THEN 1 ELSE 2 END, id", area)
        if not cola:
            st.caption("Nada pendiente.")
        for i in cola:
            lugar = nombre_esp.get(i["espacio_id"]) or i["recurso_id"]
            with st.expander(f"{COLOR_ESTADO[i['estado']]} #{i['id']} · {lugar} · {i['elemento']} · {i['prioridad']} · {i['estado']}"):
                st.write(f"**Reporte:** {i['texto']}")
                if i["origen"] == "ia":
                    st.write(f"**IA:** {i['resumen']} — {i['justificacion']} (confianza {i['confianza']:.2f})")
                st.write(f"**Motivo:** {i['motivo']}")
                if json.loads(i["ids_afectados"] or "[]"):
                    st.write(f"**IDs:** {', '.join(json.loads(i['ids_afectados']))}")
                c1, c2, c3, c4 = st.columns(4)
                if i["estado"] == "pendiente_verificacion":
                    if c1.button("Confirmar", key=f"conf_{i['id']}", type="primary"):
                        avisar("success", s.verificar(con, cfg, i["id"], "confirmar", pid))
                        st.rerun()
                    nueva = c3.selectbox("Prioridad", cfg["incidencias"]["prioridades"], key=f"np_{i['id']}",
                                         index=cfg["incidencias"]["prioridades"].index(i["prioridad"]))
                    if c4.button("Reclasificar", key=f"rec_{i['id']}"):
                        avisar("info", s.verificar(con, cfg, i["id"], "reclasificar", pid, nueva))
                        st.rerun()
                if c2.button("Descartar" if i["estado"] != "aplicada" else "Revertir", key=f"desc_{i['id']}"):
                    avisar("info", s.verificar(con, cfg, i["id"], "descartar", pid))
                    st.rerun()
                if i["estado"] == "abierta" and c1.button("Marcar resuelta", key=f"res_{i['id']}"):
                    s.resolver(con, i["id"], pid)
                    avisar("success", f"Incidencia #{i['id']} resuelta.")
                    st.rerun()

        if rol == "administrativo":
            st.subheader("Reservas en conflicto (D2)")
            conflictos = db.filas(con, "SELECT * FROM reservas WHERE estado = 'en_conflicto' ORDER BY inicio")
            if not conflictos:
                st.caption("No hay conflictos.")
            for r in conflictos:
                with st.expander(f"⚠️ {r['id']} · {nombre_esp[r['espacio_id']]} · {r['inicio'].replace('T', ' ')} · "
                                 f"{r['asistentes'] or '?'} asistentes"):
                    st.caption(r["nota"])
                    clave = f"recom_{r['id']}"
                    if st.button("✨ Recomendar alternativa", key=f"btn_{clave}"):
                        if r["asistentes"] is None:
                            avisar("error", "La reserva no tiene número de asistentes: complételo antes de reasignar.")
                        else:
                            with st.spinner("Buscando alternativa…"):
                                st.session_state[clave] = s.recomendar(
                                    con, cfg, fechas.de_iso(r["inicio"]), fechas.de_iso(r["fin"]), r["asistentes"],
                                    excluir_espacio=r["espacio_id"], excluir_reserva=r["id"],
                                    usar_ia=st.session_state.ia_lista)
                        st.rerun()
                    rec = st.session_state.get(clave)
                    if rec and rec["elegido"]:
                        st.info(f"**{rec['elegido']['nombre']}** — {'🤖' if rec['origen'] == 'ia' else '📏'} {rec['explicacion']}")
                        destino = st.selectbox("Reasignar a", [c["id"] for c in rec["candidatos"]], key=f"dest_{r['id']}",
                                               format_func=lambda i: next(f"{c['nombre']} (aforo {c['aforo']})"
                                                                          for c in rec["candidatos"] if c["id"] == i))
                        if st.button("Confirmar reasignación", key=f"reas_{r['id']}", type="primary"):
                            mostrar_resultado(s.reasignar(con, cfg, r["id"], destino, pid), "Reserva reasignada.")
                            st.session_state.pop(clave)
                            st.rerun()
                    elif rec:
                        st.warning(rec["explicacion"])

        if rol == "ti":
            st.subheader("Rehabilitación (D3)")
            directas = [e for e in espacios if e["inhabilitacion"] == "directa"]
            for e in directas:
                if st.button(f"✅ Rehabilitar {e['nombre']}", key=f"rehab_{e['id']}"):
                    s.rehabilitar_espacio(con, e["id"], pid)
                    avisar("success", f"{e['nombre']} rehabilitado. Las reservas en conflicto no reasignadas vuelven a la normalidad.")
                    st.rerun()
            pcs = db.filas(con, "SELECT * FROM elementos WHERE tipo = 'pc' AND estado = 'danado' ORDER BY id")
            if pcs:
                c1, c2 = st.columns([3, 1])
                pc = c1.selectbox("PC dañado", [p["id"] for p in pcs])
                if c2.button("Reparar PC"):
                    danados, umbral = s.reparar_pc(con, cfg, pc, pid)
                    avisar("success", f"{pc} reparado. PCs dañados: {danados} (umbral {umbral}).")
                    st.rerun()
            for r in db.filas(con, "SELECT * FROM recursos WHERE estado IN ('danado', 'mantenimiento') ORDER BY id"):
                siguiente = "mantenimiento" if r["estado"] == "danado" else "disponible"
                if st.button(f"{r['nombre']}: {r['estado']} → {siguiente}", key=f"est_{r['id']}"):
                    mostrar_resultado(s.cambiar_estado_recurso(con, cfg, pid, r["id"], siguiente), f"{r['nombre']} → {siguiente}.")
                    st.rerun()
            if not directas and not pcs:
                st.caption("No hay espacios ni PCs por rehabilitar.")


# ═══ Datos y auditoría ═══════════════════════════════════════════════════
if "Datos y auditoría" in tabs:
    with tabs["Datos y auditoría"]:
        imp = db.fila(con, "SELECT * FROM auditoria WHERE accion = 'importacion' ORDER BY id DESC LIMIT 1")
        if imp:
            st.subheader("Última importación")
            resumen = json.loads(imp["detalle"])
            st.dataframe([{"Archivo": k, "Importados": v["importados"], "Cuarentena": v["cuarentena"],
                           "Avisos": "; ".join(v["avisos"])} for k, v in resumen.items()], hide_index=True)
        st.subheader("Cuarentena")
        st.caption("Registros inconsistentes: nunca se borran. Ajuste la configuración y use «Reimportar datos».")
        st.dataframe([{"Archivo": q["archivo"], "Motivo": q["motivo"], "Fila": q["fila"]} for q in importador.cuarentena(con)],
                     hide_index=True, width="stretch")
        st.subheader("Auditoría")
        st.dataframe(db.filas(con, "SELECT momento, actor, accion, detalle FROM auditoria ORDER BY id DESC LIMIT 100"),
                     hide_index=True, width="stretch")
