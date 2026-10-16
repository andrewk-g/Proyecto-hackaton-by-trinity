"""Persistencia en SQLite. Los CSV originales nunca se modifican (P5)."""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

RUTA_DB = Path(os.getenv("CAMPUS_DB", Path(__file__).resolve().parent.parent / "data" / "campus.db"))

ESQUEMA = """
CREATE TABLE IF NOT EXISTS personas (id TEXT PRIMARY KEY, nombre TEXT, rol_dataset TEXT, rol TEXT);
CREATE TABLE IF NOT EXISTS espacios (
    id TEXT PRIMARY KEY, nombre TEXT, aforo INTEGER,
    estado TEXT DEFAULT 'disponible',          -- disponible | inhabilitado
    inhabilitacion TEXT                         -- directa | derivada | NULL
);
CREATE TABLE IF NOT EXISTS elementos (
    id TEXT PRIMARY KEY, espacio_id TEXT, tipo TEXT,
    estado TEXT DEFAULT 'operativo'             -- operativo | danado
);
CREATE TABLE IF NOT EXISTS recursos (
    id TEXT PRIMARY KEY, nombre TEXT, tipo_dataset TEXT, pool TEXT,
    estado_dataset TEXT, estado TEXT            -- disponible | prestado | danado | mantenimiento
);
CREATE TABLE IF NOT EXISTS reservas (
    id TEXT PRIMARY KEY, espacio_id TEXT, persona_id TEXT, inicio TEXT, fin TEXT,
    asistentes INTEGER, estado_dataset TEXT,
    estado TEXT,                                -- confirmada | finalizada | pendiente | cancelada | en_conflicto
    nota TEXT
);
CREATE TABLE IF NOT EXISTS prestamos (
    id TEXT PRIMARY KEY, recurso_id TEXT, persona_id TEXT, inicio TEXT,
    fin_esperado TEXT, devolucion_real TEXT, observacion TEXT
);
CREATE TABLE IF NOT EXISTS incidencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT, creada TEXT, persona_id TEXT,
    espacio_id TEXT, recurso_id TEXT, elemento TEXT, ids_afectados TEXT, texto TEXT,
    prioridad TEXT, confianza REAL, resumen TEXT, justificacion TEXT, area TEXT,
    origen TEXT,                                -- ia | manual
    estado TEXT,                                -- aplicada | pendiente_verificacion | descartada | resuelta
    motivo TEXT
);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT, momento TEXT, actor TEXT, accion TEXT, detalle TEXT
);
CREATE TABLE IF NOT EXISTS cuarentena (
    id INTEGER PRIMARY KEY AUTOINCREMENT, archivo TEXT, fila TEXT, motivo TEXT
);
CREATE TABLE IF NOT EXISTS correcciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, archivo TEXT, registro TEXT, detalle TEXT
);
"""


def conectar():
    RUTA_DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(RUTA_DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def reiniciar():
    if RUTA_DB.exists():
        RUTA_DB.unlink()
    return conectar()


def auditar(con, actor, accion, detalle):
    con.execute(
        "INSERT INTO auditoria (momento, actor, accion, detalle) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), actor, accion,
         json.dumps(detalle, ensure_ascii=False, default=str)),
    )
    con.commit()


def filas(con, sql, *params):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def fila(con, sql, *params):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None
