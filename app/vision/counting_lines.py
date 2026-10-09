from dataclasses import dataclass, field

from ..core.app_config import AppConfig

MAX_LINES = 4
_DEFAULT = ([0.15, 0.65], [0.85, 0.65])


def _clamp(point):
    """Limita un punto normalizado al rango 0..1."""
    return [max(0.0, min(1.0, float(point[0]))), max(0.0, min(1.0, float(point[1])))]


# --- Línea de conteo ---

@dataclass
class CountLine:
    """Línea de conteo configurable (hasta MAX_LINES), guardada en vision.conf [line_N]."""

    id: str                       # "line_1"
    name: str
    a: list = field(default_factory=lambda: list(_DEFAULT[0]))
    b: list = field(default_factory=lambda: list(_DEFAULT[1]))
    pos_count: int = 0            # cruces en un sentido
    neg_count: int = 0            # cruces en el otro sentido

    @property
    def total(self):
        """Devuelve el total de cruces en ambos sentidos."""
        return self.pos_count + self.neg_count

    def to_pixels(self, width, height):
        """Convierte los extremos A y B a pixeles para el tamaño indicado."""
        return ((self.a[0] * width, self.a[1] * height), (self.b[0] * width, self.b[1] * height))


# --- Persistencia en vision.conf ---

def load_lines():
    """Lee las líneas de vision.conf; si no hay ninguna válida, crea line_1."""
    cfg = AppConfig.get_instance()
    lines = []
    for section in cfg.sections("vision"):
        if not section.startswith("line_"):
            continue
        data = cfg.section("vision", section)
        a, b = data.get("a"), data.get("b")
        if isinstance(a, list) and isinstance(b, list) and len(a) == 2 and len(b) == 2:
            name = str(data.get("name", section.replace("_", " ").capitalize()))
            lines.append(CountLine(section, name, _clamp(a), _clamp(b)))

    if not lines:
        lines.append(CountLine("line_1", "Línea 1"))
    return lines[:MAX_LINES]


def save_lines(lines):
    """Escribe todas las líneas en vision.conf y borra las secciones de las que ya no existen."""
    cfg = AppConfig.get_instance()
    ids = {l.id for l in lines}
    for section in cfg.sections("vision"):
        if section.startswith("line_") and section not in ids:
            cfg.remove_section("vision", section)
    for line in lines:
        cfg.set("vision", line.id, "name", line.name)
        cfg.set("vision", line.id, "a", [round(v, 4) for v in line.a])
        cfg.set("vision", line.id, "b", [round(v, 4) for v in line.b])


def new_id(lines):
    """Devuelve el primer ID libre (line_N) y su número, o (None, None) si no hay espacio."""
    used = {l.id for l in lines}
    for n in range(1, MAX_LINES + 1):
        if f"line_{n}" not in used:
            return f"line_{n}", n
    return None, None
