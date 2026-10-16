"""Lectura de fechas en varios formatos (los datos oficiales pueden venir sucios)."""
import re
from datetime import datetime, timedelta

FORMATOS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M")


def ahora():
    return datetime.now().replace(second=0, microsecond=0)


def leer(texto, base=None):
    """Acepta ISO, dd/mm/aaaa y, en datos de ejemplo, fechas relativas
    ('AHORA-60m', 'HOY+1 08:00') para que la demo funcione cualquier día."""
    t = (texto or "").strip()
    if not t:
        return None
    base = base or ahora()
    m = re.fullmatch(r"AHORA([+-]\d+)m", t, re.I)
    if m:
        return base + timedelta(minutes=int(m.group(1)))
    m = re.fullmatch(r"HOY([+-]\d+)?\s+(\d{1,2}):(\d{2})", t, re.I)
    if m:
        dia = base + timedelta(days=int(m.group(1) or 0))
        return dia.replace(hour=int(m.group(2)), minute=int(m.group(3)))
    for f in FORMATOS:
        try:
            return datetime.strptime(t, f)
        except ValueError:
            pass
    raise ValueError(f"fecha no reconocida: '{t}'")


def iso(dt):
    return dt.isoformat(timespec="minutes") if dt else None


def de_iso(texto):
    return datetime.fromisoformat(texto) if texto else None
