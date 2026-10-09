import math
import threading
from collections import deque

import cv2
import numpy as np

from ..core.app_config import AppConfig

_CLASS_WIDTH = {
    "car": "car_width_m",
    "motorcycle": "motorcycle_width_m",
    "bus": "bus_width_m",
    "truck": "truck_width_m",
}


# --- Utilidades ---

def read_points(text, count):
    """Convierte 'x,y; x,y; ...' en [[x, y], ...], o devuelve None si no hay count puntos validos."""
    try:
        points = [[float(v) for v in pair.split(",")] for pair in str(text).split(";") if pair.strip()]
    except ValueError:
        return None
    return points if len(points) == count and all(len(p) == 2 for p in points) else None


def points_text(points):
    """Convierte [[x, y], ...] en el texto 'x, y; x, y; ...' que se guarda en vision.conf."""
    return "; ".join(f"{x:.4f}, {y:.4f}" for x, y in points)


def slope(ts, values):
    """Devuelve la pendiente de la recta de mínimos cuadrados de values respecto a ts."""
    n = len(ts)
    if n < 2:
        return 0.0
    tm = sum(ts) / n
    vm = sum(values) / n
    den = sum((t - tm) ** 2 for t in ts)
    return sum((t - tm) * (v - vm) for t, v in zip(ts, values)) / den if den > 1e-9 else 0.0


# --- Calibrador espacial ---

class SpatialCalibrator:
    """Convierte pixeles a metros para medir la velocidad de los vehículos.

    Modos (vision.conf [calibration] mode):
      plane   (recomendado) Se marcan sobre la calzada las 4 esquinas de un rectangulo
              de medidas conocidas (p. ej. ancho del carril x largo de una raya
              discontinua). Con eso se calcula la vista desde arriba (homografia) y
              cualquier punto de la calle se convierte a metros, en cualquier dirección
              y a cualquier distancia de la cámara.
      auto    Aprende la escala observando los vehículos detectados. Un auto mide
              ~1.8 m de ancho; si su caja mide 90 px, ahí 1 m = 50 px. Como los vehículos
              lejanos (arriba en la imagen) se ven más pequeños, la escala se ajusta como
              una recta según la altura: px/m = a + b·y. Es aproximada: mide bien el
              movimiento de lado a lado, pero los vehículos que se acercan o alejan de
              la cámara salen más lentos.
      manual  Un segmento de largo conocido marcado sobre el video. Usa una sola escala
              para toda la imagen: solo sirve si la cámara mira de frente.
    La velocidad se calcula con una recta ajustada a la posición del vehículo durante
    ~1 s (no con dos puntos sueltos), así el temblor de la caja no la altera.
    """

    def __init__(self):
        """Prepara el calibrador sin muestras y lee los parámetros de vision.conf."""
        self._lock = threading.Lock()
        self._samples = deque(maxlen=600)   # (y_norm, px_por_m_norm)
        self.width = self.height = 1
        self.a = self.b = 0.0
        self.reload()

    # --- Configuración ---

    def reload(self):
        """Lee vision.conf [calibration], calcula la homografia del plano y recupera la escala guardada."""
        cfg = AppConfig.get_instance()
        c = cfg.section("vision", "calibration")
        self.mode = str(c.get("mode", "auto")).lower()
        self.ref_a = c.get("ref_a", [0.3, 0.8])
        self.ref_b = c.get("ref_b", [0.7, 0.8])
        self.ref_meters = max(0.1, float(c.get("ref_meters", 3.5)))
        self.widths = {cls_name: float(c.get(key, 1.8)) for cls_name, key in _CLASS_WIDTH.items()}
        self.min_samples = int(c.get("min_samples", 25))
        # Homografia del rectangulo marcado a metros sobre la calzada
        self.plane_points = read_points(c.get("plane_points", ""), 4)
        self.plane_width = max(0.1, float(c.get("plane_width_m", 3.5)))
        self.plane_length = max(0.1, float(c.get("plane_length_m", 6.0)))
        self._homography = None
        if self.plane_points:
            target = np.float32([[0, 0], [self.plane_width, 0],
                                  [self.plane_width, self.plane_length], [0, self.plane_length]])
            try:
                self._homography = cv2.getPerspectiveTransform(np.float32(self.plane_points), target)
            except cv2.error:
                self._homography = None
        self.max_speed = float(c.get("max_speed_kmh", 160))
        # La escala automática guardada solo se usa si aún no hay muestras nuevas
        with self._lock:
            if not self._samples:
                self.a = float(c.get("auto_a", 0) or 0)
                self.b = float(c.get("auto_b", 0) or 0)
                self._saved_count = int(c.get("auto_samples", 0) or 0)

    def set_frame_size(self, width, height):
        """Guarda el tamaño del cuadro en pixeles."""
        self.width, self.height = max(1, int(width)), max(1, int(height))

    # --- Modo automático ---

    def observe(self, cls_name, bbox, conf):
        """Agrega una muestra de tamaño si la caja es confiable y completa."""
        if self.mode not in ("auto", "plane") or conf < 0.5:   # en plano sirve de respaldo
            return
        real_width = self.widths.get(str(cls_name).lower())
        if not real_width:
            return
        # Descarta cajas cortadas, muy pequeñas o de proporción extraña
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1
        margin = 4
        if x1 <= margin or y1 <= margin or x2 >= self.width - margin or y2 >= self.height - margin:
            return  # caja cortada por el borde
        if w < 12 or h < 12 or not 0.4 <= w / h <= 4.0:
            return
        with self._lock:
            self._samples.append((y2 / self.height, (w / self.width) / real_width))
            if len(self._samples) % 20 == 0:
                self._fit()

    def _fit(self):
        """Ajusta la recta px/m = a + b·y a las muestras, descartando valores atipicos."""
        data = np.array(self._samples, dtype=float)
        if len(data) < max(8, self.min_samples // 2):
            return
        y, ppm = data[:, 0], data[:, 1]
        for _ in range(2):  # ajuste robusto: descarta atipicos y reajusta
            if np.ptp(y) < 0.05:
                a, b = float(np.median(ppm)), 0.0
            else:
                b, a = np.polyfit(y, ppm, 1)
            residual = ppm - (a + b * y)
            mad = np.median(np.abs(residual - np.median(residual))) + 1e-9
            mask = np.abs(residual) <= 3 * mad
            if mask.sum() < 8:
                break
            y, ppm = y[mask], ppm[mask]
        if b < 0:  # lo lejano no puede verse más grande que lo cercano
            a, b = float(np.median(ppm)), 0.0
        self.a, self.b = float(a), float(b)

    def reset_auto(self):
        """Olvida la escala aprendida y empieza a aprender de nuevo."""
        with self._lock:
            self._samples.clear()
            self.a = self.b = 0.0
            self._saved_count = 0

    @property
    def samples(self):
        """Devuelve el número de muestras, contando las guardadas en vision.conf."""
        return max(len(self._samples), getattr(self, "_saved_count", 0))

    @property
    def auto_ready(self):
        """Indica si la escala automática tiene muestras suficientes y es positiva."""
        return self.samples >= self.min_samples and (self.a + self.b * 0.5) > 0

    def data_to_save(self):
        """Devuelve (auto_a, auto_b, auto_samples) para guardar en vision.conf."""
        with self._lock:
            return round(self.a, 6), round(self.b, 6), self.samples

    # --- Conversión ---

    def _px_per_meter(self, y_px):
        """Devuelve los pixeles por metro a la altura y_px de la imagen."""
        if self.mode in ("auto", "plane") and self.auto_ready:
            y = y_px / self.height
            value = (self.a + self.b * y) * self.width
            if value > 0.5:
                return value
        # Modo manual (o auto sin datos suficientes): escala del segmento de referencia
        dx = (self.ref_b[0] - self.ref_a[0]) * self.width
        dy = (self.ref_b[1] - self.ref_a[1]) * self.height
        return max(0.5, math.hypot(dx, dy) / self.ref_meters)

    @property
    def plane_ready(self):
        """Indica si hay un plano marcado con homografia válida."""
        return self._homography is not None

    def to_meters(self, point):
        """Convierte un punto en pixeles a (x, y) en metros sobre la calzada (solo modo plane)."""
        x, y = point[0] / self.width, point[1] / self.height
        h = self._homography
        w = h[2, 0] * x + h[2, 1] * y + h[2, 2]
        if abs(w) < 1e-9:
            return 0.0, 0.0
        return (h[0, 0] * x + h[0, 1] * y + h[0, 2]) / w, (h[1, 0] * x + h[1, 1] * y + h[1, 2]) / w

    def meters_between(self, p0, p1):
        """Devuelve la distancia en metros entre dos puntos en pixeles."""
        if self.mode == "plane" and self.plane_ready:
            (x0, y0), (x1, y1) = self.to_meters(p0), self.to_meters(p1)
            return math.hypot(x1 - x0, y1 - y0)
        distance_px = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        return distance_px / self._px_per_meter((p0[1] + p1[1]) / 2)

    def trajectory_speed(self, points):
        """Calcula la velocidad (km/h) con una recta ajustada a [(t, x, y), ...] en pixeles."""
        if len(points) < 3 or points[-1][0] - points[0][0] < 0.3:
            return None
        if self.mode == "plane" and not self.plane_ready and not self.auto_ready:
            return None   # sin plano marcado ni escala aprendida: mejor no mostrar una velocidad falsa
        ts = [p[0] - points[0][0] for p in points]
        if self.mode == "plane" and self.plane_ready:
            meters = [self.to_meters((p[1], p[2])) for p in points]
            vx = slope(ts, [m[0] for m in meters])
            vy = slope(ts, [m[1] for m in meters])
        else:
            y_avg = sum(p[2] for p in points) / len(points)
            scale = self._px_per_meter(y_avg)
            vx = slope(ts, [p[1] for p in points]) / scale
            vy = slope(ts, [p[2] for p in points]) / scale
        return min(self.max_speed, math.hypot(vx, vy) * 3.6)

    @property
    def ready(self):
        """Indica si el modo actual ya puede medir velocidades."""
        if self.mode == "plane":
            return self.plane_ready
        return self.mode == "manual" or self.auto_ready

    def summary(self):
        """Devuelve un texto corto para el panel del video y la configuración."""
        if self.mode == "plane":
            if self.plane_ready:
                return f"Plano · {self.plane_width:g} x {self.plane_length:g} m"
            return "Plano · sin marcar (usa Calibrar)"
        if self.mode == "auto":
            if self.auto_ready:
                near = self._px_per_meter(self.height * 0.9)
                far = self._px_per_meter(self.height * 0.3)
                return f"Auto · {near:.0f}/{far:.0f} px/m · {self.samples} muestras"
            return f"Auto · aprendiendo ({self.samples}/{self.min_samples})"
        return f"Manual · {self._px_per_meter(0):.1f} px/m"
