from dataclasses import dataclass, field

from ..core.app_config import AppConfig
from .geometry import point_in_polygon

_DEFAULT = ([0.05, 0.05], [0.95, 0.05], [0.95, 0.95], [0.05, 0.95])


# --- Lectura de puntos ---

def _clamp(point):
    """Limita un punto normalizado al rango 0..1 y lo redondea a 4 decimales."""
    return [round(max(0.0, min(1.0, float(point[0]))), 4), round(max(0.0, min(1.0, float(point[1]))), 4)]


def _read_points(text):
    """Convierte 'x,y; x,y; ...' en [[x, y], ...], o devuelve None si no es válido."""
    try:
        points = [_clamp(pair.split(",")) for pair in str(text).split(";") if pair.strip()]
    except (ValueError, IndexError):
        return None
    return points if len(points) >= 3 else None


# --- Zona de detección ---

@dataclass
class DetectionZone:
    """Poligono sobre el video fuera del cual se ignoran las detecciones.

    Sirve para descartar letreros, vallas publicitarias, estacionamientos o la
    acera: solo cuentan los vehículos cuyo punto de apoyo (centro inferior de la
    caja) queda dentro de la zona. Se dibuja y se edita desde la página Cámara.
    """

    active: bool = False
    points: list = field(default_factory=lambda: [list(p) for p in _DEFAULT])

    def to_pixels(self, width, height):
        """Convierte los puntos normalizados a pixeles para el tamaño indicado."""
        return [(x * width, y * height) for x, y in self.points]

    def contains(self, point, width, height):
        """Indica si el punto (en pixeles) esta dentro de la zona, o si la zona no esta activa."""
        if not self.active:
            return True
        return point_in_polygon((point[0] / max(1, width), point[1] / max(1, height)), self.points)

    def copy_zone(self):
        """Devuelve una copia independiente de la zona."""
        return DetectionZone(self.active, [list(p) for p in self.points])


# --- Persistencia en vision.conf [zone] ---

def load_zone():
    """Lee la zona de vision.conf, con el rectangulo por defecto si los puntos no son validos."""
    data = AppConfig.get_instance().section("vision", "zone")
    points = _read_points(data.get("points", "")) or [list(p) for p in _DEFAULT]
    return DetectionZone(bool(data.get("active", False)), points)


def save_zone(zone):
    """Guarda el estado y los puntos de la zona en vision.conf."""
    cfg = AppConfig.get_instance()
    cfg.set("vision", "zone", "active", bool(zone.active))
    cfg.set("vision", "zone", "points", "; ".join(f"{x:.4f}, {y:.4f}" for x, y in zone.points))
