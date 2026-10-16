"""Mapa SVG de la planta del campus, coloreado según el estado en vivo de cada espacio.
Geometría basada en el plano del proyecto de diseño del equipo."""

# nombre del espacio → forma SVG (viewBox 1000 x 2100)
FORMAS = {
    "Sputnik":   ("rect", (660, 160, 280, 340)),
    "Apolo":     ("rect", (660, 520, 280, 360)),
    "Artemis":   ("rect", (60, 1020, 380, 360)),
    "Cosmos":    ("rect", (460, 1020, 280, 360)),
    "Auditorio": ("path", "M 60,1400 L 520,1400 L 520,1720 L 380,1720 L 320,1780 L 60,1780 Z"),
    "Skilab":    ("rect", (540, 1400, 400, 380)),
    "Blanca":    ("rect", (60, 1800, 280, 230)),
    "Azul":      ("rect", (360, 1800, 280, 230)),
    "Amarillas": ("rect", (660, 1800, 135, 230)),
    "Verdes":    ("rect", (805, 1800, 135, 230)),
}

COLORES = {
    "disponible":   ("#10b981", "#34d399"),
    "aviso":        ("#d97706", "#fbbf24"),
    "inhabilitado": ("#e11d48", "#fb7185"),
}


def _centro(tipo, geo):
    if tipo == "rect":
        x, y, w, h = geo
        return x + w / 2, y + h / 2
    return 290, 1590   # Auditorio


def svg(espacios, avisos_por_id):
    """espacios: filas de la BD; avisos_por_id: {id: [avisos]}."""
    zonas, etiquetas = [], []
    for e in espacios:
        if e["nombre"] not in FORMAS:
            continue
        tipo, geo = FORMAS[e["nombre"]]
        if e["estado"] == "inhabilitado":
            estado, detalle = "inhabilitado", f"⛔ {e['inhabilitacion']}"
        elif avisos_por_id.get(e["id"]):
            estado, detalle = "aviso", f"⚠ {len(avisos_por_id[e['id']])} aviso(s)"
        else:
            estado, detalle = "disponible", "✓ disponible"
        relleno, borde = COLORES[estado]
        estilo = f'fill="{relleno}" fill-opacity="0.22" stroke="{borde}" stroke-width="3"'
        titulo = f"<title>{e['nombre']} · aforo {e['aforo']} · {detalle}</title>"
        if tipo == "rect":
            x, y, w, h = geo
            zonas.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" {estilo}>{titulo}</rect>')
        else:
            zonas.append(f'<path d="{geo}" {estilo}>{titulo}</path>')
        cx, cy = _centro(tipo, geo)
        chico = e["aforo"] < 10
        etiquetas.append(
            f'<text x="{cx}" y="{cy - 12}" fill="#ffffff" font-size="{22 if not chico else 17}" font-weight="700" '
            f'text-anchor="middle">{e["nombre"].upper()}</text>'
            f'<text x="{cx}" y="{cy + 16}" fill="{borde}" font-size="{16 if not chico else 13}" '
            f'text-anchor="middle">Aforo {e["aforo"]}</text>'
            f'<text x="{cx}" y="{cy + 42}" fill="{borde}" font-size="{15 if not chico else 12}" '
            f'text-anchor="middle">{detalle}</text>')
    return (
        '<svg viewBox="0 0 1000 2100" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;max-height:820px;font-family:Inter,sans-serif">'
        '<defs><pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">'
        '<path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="1"/></pattern></defs>'
        '<rect width="1000" height="2100" fill="#0b1120" rx="16"/>'
        '<rect width="1000" height="2100" fill="url(#grid)" rx="16"/>'
        + "".join(zonas) + "".join(etiquetas) + "</svg>")
