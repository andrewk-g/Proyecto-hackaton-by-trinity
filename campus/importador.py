"""Importa los CSV a SQLite. Lo inconsistente va a cuarentena con su motivo (nunca se borra)."""
import csv
import json
from pathlib import Path

from campus import config as conf
from campus import fechas
from campus.db import auditar, filas

ARCHIVOS = ("personas", "espacios", "recursos", "reservas", "prestamos")


def _leer_csv(ruta):
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()} for fila in csv.DictReader(f)]


def _cuarentena(con, archivo, fila, motivo, resumen):
    con.execute("INSERT INTO cuarentena (archivo, fila, motivo) VALUES (?, ?, ?)",
                (archivo, json.dumps(fila, ensure_ascii=False), motivo))
    resumen[archivo]["cuarentena"] += 1


def _significado(catalogo, valor):
    """D4: el valor del dataset se busca en la configuración ignorando mayúsculas y espacios."""
    v = valor.strip().lower()
    for clave, sig in catalogo.items():
        if clave.strip().lower() == v:
            return sig
    return None


def _crear_elementos(con, cfg, esp_id, nombre, aforo):
    for clave in conf.elementos_de_espacio(cfg, nombre):
        if clave == "pc":
            pref = nombre[:3].upper()
            for n in range(1, aforo + 1):   # un PC por puesto
                con.execute("INSERT INTO elementos (id, espacio_id, tipo) VALUES (?, ?, ?)",
                            (f"PC-{pref}-{n:02d}", esp_id, "pc"))
        else:
            con.execute("INSERT INTO elementos (id, espacio_id, tipo) VALUES (?, ?, ?)",
                        (f"{esp_id}-{clave}", esp_id, clave))


def importar(con, cfg, carpeta, actor="sistema"):
    carpeta = Path(carpeta)
    resumen = {a: {"importados": 0, "corregidos": 0, "cuarentena": 0, "avisos": []} for a in ARCHIVOS}
    datos = {a: _leer_csv(carpeta / f"{a}.csv") for a in ARCHIVOS}
    cat = cfg["catalogos"]

    # ── Personas ────────────────────────────────────────────────
    ids = set()
    for f in datos["personas"]:
        if not f.get("id") or f["id"] in ids:
            _cuarentena(con, "personas", f, "ID vacío o duplicado", resumen)
            continue
        rol = _significado(cat["roles"], f.get("rol", ""))
        if not rol:
            _cuarentena(con, "personas", f, f"Rol '{f.get('rol')}' no reconocido", resumen)
            continue
        ids.add(f["id"])
        con.execute("INSERT INTO personas VALUES (?, ?, ?, ?)", (f["id"], f["nombre"], f["rol"], rol))
        resumen["personas"]["importados"] += 1
    personas = ids

    # ── Espacios ────────────────────────────────────────────────
    ids, aforos = set(), {}
    for f in datos["espacios"]:
        if not f.get("id") or f["id"] in ids:
            _cuarentena(con, "espacios", f, "ID vacío o duplicado", resumen)
            continue
        try:
            aforo = int(f.get("aforo", ""))
        except ValueError:
            aforo = 0
        if aforo <= 0:
            _cuarentena(con, "espacios", f, f"Aforo inválido: '{f.get('aforo')}'", resumen)
            continue
        ids.add(f["id"])
        aforos[f["id"]] = aforo
        con.execute("INSERT INTO espacios (id, nombre, aforo) VALUES (?, ?, ?)", (f["id"], f["nombre"], aforo))
        _crear_elementos(con, cfg, f["id"], f["nombre"], aforo)
        resumen["espacios"]["importados"] += 1
    espacios = ids

    # ── Recursos ────────────────────────────────────────────────
    ids = set()
    tiene_tipo = bool(datos["recursos"]) and "tipo" in datos["recursos"][0]
    if datos["recursos"] and not tiene_tipo:
        resumen["recursos"]["avisos"].append("Sin columna de tipo: todos los recursos van al pool 'General' (portátil)")
    for f in datos["recursos"]:
        if not f.get("id") or f["id"] in ids:
            _cuarentena(con, "recursos", f, "ID vacío o duplicado", resumen)
            continue
        pool = conf.pool_de_tipo(cfg, f.get("tipo")) if tiene_tipo else "general"
        if not pool:
            _cuarentena(con, "recursos", f, f"Tipo '{f.get('tipo')}' no pertenece a ningún pool", resumen)
            continue
        estado = _significado(cat["estados_recurso"], f.get("estado", ""))
        if not estado:
            _cuarentena(con, "recursos", f, f"Estado '{f.get('estado')}' no reconocido", resumen)
            continue
        ids.add(f["id"])
        con.execute("INSERT INTO recursos VALUES (?, ?, ?, ?, ?, ?)",
                    (f["id"], f["nombre"], f.get("tipo"), pool, f.get("estado"), estado))
        resumen["recursos"]["importados"] += 1
    recursos = ids

    # ── Reservas ────────────────────────────────────────────────
    ids = set()
    for f in datos["reservas"]:
        if not f.get("id") or f["id"] in ids:
            _cuarentena(con, "reservas", f, "ID vacío o duplicado", resumen)
            continue
        if f.get("espacio_id") not in espacios:
            _cuarentena(con, "reservas", f, f"Espacio '{f.get('espacio_id')}' no existe", resumen)
            continue
        if f.get("persona_id") not in personas:
            _cuarentena(con, "reservas", f, f"Persona '{f.get('persona_id')}' no existe", resumen)
            continue
        try:
            ini, fin = fechas.leer(f.get("inicio")), fechas.leer(f.get("fin"))
        except ValueError as e:
            _cuarentena(con, "reservas", f, str(e), resumen)
            continue
        if not ini or not fin or fin <= ini:
            _cuarentena(con, "reservas", f, "Fechas inconsistentes (fin antes del inicio o vacías)", resumen)
            continue
        estado = _significado(cat["estados_reserva"], f.get("estado", ""))
        if not estado:
            _cuarentena(con, "reservas", f, f"Estado '{f.get('estado')}' no reconocido", resumen)
            continue
        asist = int(f["asistentes"]) if f.get("asistentes", "").isdigit() else None
        nota = None
        if asist is None:
            nota = "Asistentes desconocido"
        elif asist > aforos[f["espacio_id"]]:
            nota = f"Inconsistente: {asist} asistentes exceden el aforo ({aforos[f['espacio_id']]})"
        if nota:
            resumen["reservas"]["avisos"].append(f"{f['id']}: {nota}")
        ids.add(f["id"])
        con.execute("INSERT INTO reservas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f["id"], f["espacio_id"], f["persona_id"], fechas.iso(ini), fechas.iso(fin),
                     asist, f.get("estado"), estado, nota))
        resumen["reservas"]["importados"] += 1

    # ── Préstamos ───────────────────────────────────────────────
    ids = set()
    for f in datos["prestamos"]:
        if not f.get("id") or f["id"] in ids:
            _cuarentena(con, "prestamos", f, "ID vacío o duplicado", resumen)
            continue
        if f.get("recurso_id") not in recursos or f.get("persona_id") not in personas:
            _cuarentena(con, "prestamos", f, "Recurso o persona inexistente", resumen)
            continue
        try:
            ini = fechas.leer(f.get("inicio"))
            esp = fechas.leer(f.get("fin_esperado"))
            dev = fechas.leer(f.get("devolucion_real"))
        except ValueError as e:
            _cuarentena(con, "prestamos", f, str(e), resumen)
            continue
        if not ini or not esp or esp <= ini or (dev and dev < ini):
            _cuarentena(con, "prestamos", f, "Fechas inconsistentes", resumen)
            continue
        ids.add(f["id"])
        con.execute("INSERT INTO prestamos VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f["id"], f["recurso_id"], f["persona_id"], fechas.iso(ini), fechas.iso(esp),
                     fechas.iso(dev), "sin observaciones" if dev else None))
        if not dev:   # coherencia: un préstamo abierto implica recurso prestado
            con.execute("UPDATE recursos SET estado = 'prestado' WHERE id = ? AND estado = 'disponible'",
                        (f["recurso_id"],))
        resumen["prestamos"]["importados"] += 1

    con.commit()
    auditar(con, actor, "importacion", resumen)
    return resumen


def cuarentena(con):
    return filas(con, "SELECT * FROM cuarentena ORDER BY archivo, id")
