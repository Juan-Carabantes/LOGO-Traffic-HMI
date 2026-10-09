import math
import unicodedata
from datetime import datetime

import cv2
import numpy as np

from ..core.app_config import AppConfig
from ..core.formatting import hex_to_bgr
from .detector import CLASS_LABELS

_SOURCE = cv2.FONT_HERSHEY_SIMPLEX
_AA = cv2.LINE_AA


# --- Texto y rectangulos ---

def ascii_safe(text):
    """Convierte el texto a ASCII, porque OpenCV solo dibuja ASCII: quita acentos y cambia '·' por '-'."""
    text = str(text).replace("·", "-").replace("–", "-").replace("—", "-").replace("≈", "~")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _translucent_rect(frame, x1, y1, x2, y2, color, opacity):
    """Dibuja un rectangulo relleno semitransparente, recortado a los bordes del cuadro."""
    height, width = frame.shape[:2]
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(width, int(x2)), min(height, int(y2))
    if x2 <= x1 or y2 <= y1:
        return
    region = frame[y1:y2, x1:x2]
    layer = np.full_like(region, color, dtype=np.uint8)
    cv2.addWeighted(layer, opacity, region, 1 - opacity, 0, dst=region)


_OUTLINE = ((-1, -1), (1, -1), (-1, 1), (1, 1))


def _text(frame, text, x, y, scale, color, thickness=1):
    """Dibuja texto con contorno oscuro para leerse sobre cualquier fondo.

    El contorno se hace con el mismo grosor desplazado 1 px: en OpenCV 5 un trazo
    más grueso cambia el ancho de las letras y el contorno quedaba corrido.
    """
    text = ascii_safe(text)
    x, y = int(x), int(y)
    for dx, dy in _OUTLINE:
        cv2.putText(frame, text, (x + dx, y + dy), _SOURCE, scale, (0, 0, 0), thickness, _AA)
    cv2.putText(frame, text, (x, y), _SOURCE, scale, color, thickness, _AA)


# --- Dibujo sobre el video ---

class OverlayRenderer:
    """Dibuja sobre el video; lo dibujado queda también en las grabaciones.

    Dibuja el panel de información (fecha y hora, fuente, FPS, conteo, calibración),
    la zona de detección (lo de afuera se oscurece), las líneas de conteo con nombre,
    flecha de sentido y cruces por sentido, las cajas con etiqueta (tipo, ID,
    velocidad) y estela de cada vehículo, y el indicador REC.
    Colores: theme.conf [Video_overlay]. Opciones: vision.conf [display] y camera.conf [hud].
    """

    def __init__(self):
        """Prepara el dibujante con los colores y opciones actuales."""
        self.reload()

    def reload(self):
        """Lee los colores de theme.conf y las opciones de vision.conf y camera.conf."""
        cfg = AppConfig.get_instance()
        colors = cfg.section("theme", "Video_overlay")

        def c(name, fallback):
            """Devuelve el color BGR de la clave indicada, o el color de respaldo."""
            return hex_to_bgr(colors.get(name), fallback)

        self.line = c("counting_line", (63, 210, 255))
        self.point_a = c("point_a", (122, 214, 34))
        self.point_b = c("point_b", (95, 90, 255))
        self.box_counted = c("box_counted", (122, 214, 34))
        self.box_pending = c("box_pending", (255, 141, 77))
        self.background = c("label_background", (20, 14, 11))
        self.text = c("label_text", (255, 255, 255))
        self.rec = c("recording", (59, 59, 255))
        self.zone_border = c("zone", (255, 200, 80))
        self.plane_color = c("calibration", (252, 132, 192))
        self._mask = (None, None)       # (clave, mascara de lo que queda fuera de la zona)

        # Opciones de dibujo de vehículos
        self.show_boxes = cfg.get("vision", "show_boxes", default=True)
        self.show_class = cfg.get("vision", "show_class", default=True)
        self.show_speed = cfg.get("vision", "show_speed", default=True)
        self.show_trail = cfg.get("vision", "show_trail", default=True)

        # Opciones del panel de información
        hud = cfg.section("camera", "hud")
        self.hud = bool(hud.get("show", True))
        self.hud_date = bool(hud.get("show_datetime", True))
        self.hud_source = bool(hud.get("show_source", True))
        self.hud_fps = bool(hud.get("show_fps", True))
        self.hud_count = bool(hud.get("show_count", True))
        self.hud_calibration = bool(hud.get("show_calibration", True))
        self.format_date = cfg.get_text("camera", "datetime_format", "%d/%m/%Y  %H:%M:%S")
        self.opacity = max(0.0, min(1.0, float(hud.get("background_opacity", 0.55))))

    def _scale(self, frame):
        """Devuelve el factor de escala del dibujo según el ancho del cuadro (base 1280 px)."""
        return max(0.45, min(1.3, frame.shape[1] / 1280))

    # --- Zona, calibración y vehículos ---

    def zone(self, frame, zone):
        """Oscurece lo que queda fuera de la zona de detección y dibuja su borde."""
        if zone is None or not zone.active:
            return
        height, width = frame.shape[:2]
        key = (width, height, tuple(tuple(p) for p in zone.points))
        points = np.array([(int(x), int(y)) for x, y in zone.to_pixels(width, height)], np.int32)
        # La mascara solo se recalcula si cambia el tamaño o la zona
        if self._mask[0] != key:
            outside = np.full((height, width), 255, np.uint8)
            cv2.fillPoly(outside, [points], 0)
            self._mask = (key, outside)
        dark = cv2.convertScaleAbs(frame, alpha=0.45)
        cv2.copyTo(dark, self._mask[1], frame)
        cv2.polylines(frame, [points], True, self.zone_border, max(1, int(2 * self._scale(frame))), _AA)

    def draw_plane(self, frame, calibrator):
        """Dibuja el rectangulo de calibración sobre la calzada para comprobar que esta bien marcado."""
        if not self.hud_calibration or calibrator.mode != "plane" or not calibrator.plane_ready:
            return
        height, width = frame.shape[:2]
        k = self._scale(frame)
        points = np.array([(int(x * width), int(y * height)) for x, y in calibrator.plane_points], np.int32)
        cv2.polylines(frame, [points], True, self.plane_color, max(1, int(k)), _AA)
        for point in points:
            cv2.circle(frame, tuple(int(v) for v in point), max(2, int(3 * k)), self.plane_color, -1, _AA)
        x, y = points[:, 0].min(), points[:, 1].max() + int(18 * k)
        _text(frame, f"{calibrator.plane_width:g} x {calibrator.plane_length:g} m", x, min(height - 4, y),
               0.45 * k, self.plane_color)

    def vehicles(self, frame, vehicles):
        """Dibuja la estela, la caja y la etiqueta (tipo, ID, velocidad) de cada vehículo."""
        k = self._scale(frame)
        for v in vehicles:
            x1, y1, x2, y2 = (int(n) for n in v.bbox)
            color = self.box_counted if v.counted else self.box_pending

            if self.show_trail and len(v.trajectory) > 2:
                points = np.array([(int(p[1]), int(p[2])) for p in list(v.trajectory)[-30:]], np.int32)
                cv2.polylines(frame, [points], False, color, max(1, int(2 * k)), _AA)

            if not self.show_boxes:
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, max(1, int(2 * k)), _AA)

            # Etiqueta sobre la caja con fondo del color de la caja
            parts = []
            if self.show_class:
                parts.append(f"{CLASS_LABELS.get(v.class_name, v.class_name)} #{v.track_id}")
            if self.show_speed and v.speed_kmh > 0:
                parts.append(f"{v.speed_kmh:.0f} km/h")
            if parts:
                text = ascii_safe("  ".join(parts))
                scale = 0.5 * k
                (tw, th), _ = cv2.getTextSize(text, _SOURCE, scale, 1)
                y_top = max(0, y1 - th - int(10 * k))
                cv2.rectangle(frame, (x1, y_top), (x1 + tw + int(10 * k), y1), color, -1)
                cv2.putText(frame, text, (x1 + int(5 * k), y1 - int(5 * k)), _SOURCE, scale, (0, 0, 0), 1, _AA)

    def count_lines(self, frame, lines):
        """Dibuja cada línea de conteo con sus extremos A y B, la flecha de sentido y los cruces."""
        height, width = frame.shape[:2]
        k = self._scale(frame)
        for line in lines:
            (ax, ay), (bx, by) = line.to_pixels(width, height)
            a, b = (int(ax), int(ay)), (int(bx), int(by))
            cv2.line(frame, a, b, self.line, max(2, int(3 * k)), _AA)
            cv2.circle(frame, a, int(8 * k), self.point_a, -1, _AA)
            cv2.circle(frame, b, int(8 * k), self.point_b, -1, _AA)

            # Flecha del sentido positivo (perpendicular a la línea, en el centro)
            mx, my = (ax + bx) / 2, (ay + by) / 2
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1
            nx, ny = -dy / length, dx / length
            arrow = 28 * k
            cv2.arrowedLine(frame, (int(mx - nx * arrow), int(my - ny * arrow)),
                            (int(mx + nx * arrow), int(my + ny * arrow)), self.line,
                            max(1, int(2 * k)), _AA, tipLength=0.35)

            # Etiqueta con el nombre, el total y los cruces por sentido
            label = ascii_safe(f"{line.name}: {line.total}  (+{line.pos_count} / -{line.neg_count})")
            scale = 0.5 * k
            (tw, th), _ = cv2.getTextSize(label, _SOURCE, scale, 1)
            ex, ey = int(mx + 10 * k), int(my - 12 * k)
            _translucent_rect(frame, ex - 6 * k, ey - th - 6 * k, ex + tw + 6 * k, ey + 6 * k, self.background, 0.7)
            cv2.putText(frame, label, (ex, ey), _SOURCE, scale, self.line, 1, _AA)

    # --- Panel de información e indicador REC ---

    def panel_info(self, frame, info):
        """Dibuja el panel de información; info es un dict con source, fps, fps_ai, model, total, in_scene, stopped y calibration."""
        if not self.hud:
            return
        k = self._scale(frame)
        # Filas visibles según las opciones de camera.conf [hud]
        rows = []
        if self.hud_date:
            rows.append(("title", datetime.now().strftime(self.format_date)))
        if self.hud_source:
            rows.append(("", f"Fuente: {info.get('source', '-')}"))
        if self.hud_fps:
            rows.append(("", f"Video: {info.get('fps', 0):.0f} FPS   IA: {info.get('fps_ai', 0):.0f} FPS"))
            rows.append(("", f"Modelo: {info.get('model', '-')}"))
        if self.hud_count:
            rows.append(("", f"Contados: {info.get('total', 0)}   En escena: {info.get('in_scene', 0)}"
                              f"   Detenidos: {info.get('stopped', 0)}"))
        if self.hud_calibration:
            rows.append(("", f"Calibración: {info.get('calibration', '-')}"))
        if not rows:
            return

        # Fondo ajustado a la fila más ancha y texto encima
        scale, row_height, margin = 0.5 * k, int(22 * k), int(10 * k)
        rows = [(kind, ascii_safe(t)) for kind, t in rows]
        thick = max(1, int(2 * k))
        max_width = max(cv2.getTextSize(t, _SOURCE, scale * (1.2 if kind else 1), thick if kind else 1)[0][0]
                        for kind, t in rows)
        _translucent_rect(frame, margin, margin, margin * 3 + max_width, margin * 2 + row_height * len(rows),
                          self.background, self.opacity)
        y = margin * 2 + int(12 * k)
        for kind, text in rows:
            if kind == "title":
                _text(frame, text, margin * 2, y, scale * 1.2, self.text, thick)
            else:
                _text(frame, text, margin * 2, y, scale, self.text)
            y += row_height

    def rec_indicator(self, frame, seconds):
        """Dibuja el indicador REC con el tiempo de grabación y un punto que parpadea."""
        width = frame.shape[1]
        k = self._scale(frame)
        minutes, secs = divmod(int(seconds), 60)
        text = f"REC {minutes:02d}:{secs:02d}"
        (tw, _), _ = cv2.getTextSize(text, _SOURCE, 0.65 * k, 2)
        x = width - tw - int(40 * k)
        _translucent_rect(frame, x - 30 * k, 10 * k, width - 10 * k, 50 * k, self.background, self.opacity)
        if int(seconds * 2) % 2 == 0:  # parpadeo
            cv2.circle(frame, (int(x - 14 * k), int(30 * k)), int(8 * k), self.rec, -1, _AA)
        _text(frame, text, x, 38 * k, 0.65 * k, self.rec, 2)
