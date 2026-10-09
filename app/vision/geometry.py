# --- Lado y cruce de segmentos ---

def side(point, a, b):
    """Devuelve el producto cruz: > 0 a un lado de la recta A-B, < 0 al otro y 0 sobre ella."""
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def _sign(value, tolerance=1e-9):
    """Devuelve el signo del valor (-1, 0 o 1) con una tolerancia alrededor de cero."""
    return 0 if abs(value) <= tolerance else (1 if value > 0 else -1)


def crosses_segment(p0, p1, a, b):
    """Calcula el sentido del cruce del movimiento p0->p1 sobre el segmento A-B.

    Devuelve +1 o -1 según el sentido, o 0 si el movimiento no cruza el segmento.
    Tocar la línea sin pasar al otro lado no cuenta como cruce.
    """
    d0, d1 = _sign(side(p0, a, b)), _sign(side(p1, a, b))
    if d0 == 0 or d1 == 0 or d0 == d1:
        return 0
    # El segmento A-B debe quedar a ambos lados de la recta p0-p1
    e0, e1 = _sign(side(a, p0, p1)), _sign(side(b, p0, p1))
    if e0 == e1 and e0 != 0:
        return 0
    return 1 if d0 < d1 else -1


# --- Poligonos y cajas ---

def point_in_polygon(point, polygon):
    """Indica si el punto (x, y) esta dentro del poligono [(x, y), ...] con la regla par-impar."""
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def box_area(box):
    """Devuelve el área de una caja [x1, y1, x2, y2], o 0 si esta invertida."""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection(c1, c2):
    """Devuelve el área común de dos cajas [x1, y1, x2, y2]."""
    width = min(c1[2], c2[2]) - max(c1[0], c2[0])
    height = min(c1[3], c2[3]) - max(c1[1], c2[1])
    return max(0.0, width) * max(0.0, height)


def iou(c1, c2):
    """Calcula la intersección sobre union (IoU) de dos cajas [x1, y1, x2, y2]."""
    common = intersection(c1, c2)
    union = box_area(c1) + box_area(c2) - common
    return common / union if union > 0 else 0.0
