import math
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from ..core.app_config import AppConfig
from .calibration import slope
from .geometry import crosses_segment, iou, side

COUNT_CLASSES = ("car", "motorcycle", "bus", "truck", "other")
MAX_PREDICTION_S = 0.5        # no extrapolar la caja más allá de esto
IOU_REATTACH = 0.4            # una ID nueva sobre un vehículo recién perdido es el mismo vehículo


# --- Vehículo seguido ---

@dataclass
class VehicleView:
    """Copia ligera de un vehículo para dibujarlo desde otro hilo."""

    track_id: int
    class_name: str
    bbox: list
    speed_kmh: float
    counted: bool
    trajectory: list


class TrackedVehicle:
    """Estado de un vehículo seguido: caja suavizada, trayectoria, velocidad, tipo y cruces."""

    def __init__(self, track_id, class_name, bbox, confidence, now, window_s=0.5, smoothing_s=0.15):
        """Crea el vehículo con su primera detección."""
        self.track_id = track_id
        self.class_name = class_name
        self.bbox = [float(v) for v in bbox]         # caja ajustada en el instante last_seen
        self.confidence = confidence
        self.hits = 1
        self.last_seen = now
        self.window_s = window_s
        self.smoothing_s = smoothing_s
        # Movimiento suave: observaciones, pendientes y salto pendiente de repartir
        self._observations = deque(maxlen=40)          # (t, caja detectada)
        self._observations.append((now, list(self.bbox)))
        self._slope = [0.0, 0.0, 0.0, 0.0]             # px/s de x1, y1, x2, y2
        self._correction = [0.0, 0.0, 0.0, 0.0]        # salto pendiente de repartir
        self._t_correction = now
        # Trayectoria y velocidad
        self.trajectory = deque(maxlen=90)             # (t, x, y) del punto de apoyo
        self.trajectory.append((now, *self.anchor))
        self._measurements = deque(maxlen=30)          # velocidades recientes (km/h)
        self.speed_kmh = 0.0                           # valor mostrado (estable)
        self._last_publish = now
        # Conteo, votos de tipo y detección de objetos fijos
        self.counted_lines = set()
        self.sides = {}                                # line.id -> (lado, último punto a ese lado)
        self.votes = defaultdict(float)
        self.votes[class_name] += confidence
        self.origin = self.anchor                      # donde apareció
        self.max_travel = 0.0                          # desplazamiento máximo desde que apareció
        self.hidden = False                            # objeto fijo (letrero, poste...)

    @property
    def anchor(self):
        """Devuelve el centro inferior de la caja (contacto con la calzada)."""
        x1, _, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, y2)

    @property
    def counted(self):
        """Indica si el vehículo ya se conto en alguna línea."""
        return bool(self.counted_lines)

    def _fit(self, now):
        """Ajusta una recta por coordenada a las observaciones recientes y devuelve la caja en now."""
        recent = [o for o in self._observations if now - o[0] <= self.window_s]
        if len(recent) < 2:
            self._slope = [0.0, 0.0, 0.0, 0.0]
            return list(recent[-1][1])
        ts = [o[0] - now for o in recent]
        box = []
        for i in range(4):
            values = [o[1][i] for o in recent]
            m = slope(ts, values)
            mean_t = sum(ts) / len(ts)
            mean_v = sum(values) / len(values)
            box.append(mean_v - m * mean_t)       # valor de la recta en t = now
            self._slope[i] = m
        # El tamaño cambia poco: que su pendiente no deforme la caja al extrapolar
        width_m = (self._slope[2] - self._slope[0]) / 2
        height_m = (self._slope[3] - self._slope[1]) / 2
        self._slope = [self._slope[0] + width_m, self._slope[1] + height_m,
                       self._slope[2] - width_m, self._slope[3] - height_m]
        return box

    def update_state(self, bbox, conf, cls_name, now):
        """Agrega una detección nueva: vota el tipo, reajusta la caja y guarda el salto a repartir."""
        before = self.predicted_box(now)            # donde se estaba dibujando
        self._observations.append((now, [float(v) for v in bbox]))
        self.votes[cls_name] += conf
        self.class_name = max(self.votes, key=self.votes.get)
        self.bbox = self._fit(now)
        self._correction = [a - b for a, b in zip(before, self.bbox)]
        self._t_correction = now
        self.confidence = conf
        self.hits += 1
        self.last_seen = now
        # Trayectoria y desplazamiento máximo desde el origen
        self.trajectory.append((now, *self.anchor))
        x0, y0 = self.origin
        x1, y1 = self.anchor
        self.max_travel = max(self.max_travel, abs(x1 - x0), abs(y1 - y0))

    def predicted_box(self, now):
        """Devuelve la caja en el instante now: sigue la recta y reparte el último salto."""
        dt = max(0.0, min(MAX_PREDICTION_S, now - self.last_seen))
        remaining = math.exp(-max(0.0, now - self._t_correction) / self.smoothing_s) if self.smoothing_s > 0 else 0.0
        return [v + m * dt + c * remaining for v, m, c in zip(self.bbox, self._slope, self._correction)]

    def measure_speed(self, calibrator, now, window_s, interval_s):
        """Mide la velocidad con una recta sobre ~window_s; el valor visible cambia cada interval_s."""
        points = [p for p in self.trajectory if now - p[0] <= window_s]
        speed = calibrator.trajectory_speed(points)
        if speed is not None:
            self._measurements.append(speed)
        if now - self._last_publish >= interval_s and self._measurements:
            self.speed_kmh = statistics.median(self._measurements)
            self._measurements.clear()
            self._last_publish = now


# --- Seguidor y conteo ---

class VehicleTracker:
    """Sigue vehículos, los cuenta por líneas y mide una velocidad estable (vision.conf [tracking]).

    - Usa el punto de apoyo (centro inferior de la caja), que esta sobre la calzada:
      mejor para contar y para medir distancias reales.
    - Cuenta cuando ese punto cruza el segmento A-B (no la recta infinita), con su
      sentido. Admite varias líneas.
    - Un vehículo debe verse min_hits cuadros antes de contarse (evita falsos).
    - Movimiento suave: se ajusta una recta (posición = inicio + velocidad x tiempo)
      a las últimas detecciones de ~smoothing_window_s. Entre un análisis de la IA y
      el siguiente la caja sigue esa recta, y el salto de una detección nueva se
      reparte en motion_smoothing_s (sin saltos y sin retraso).
    - La velocidad se calcula con una recta ajustada a ~speed_window_s de recorrido
      y lo que se muestra se actualiza cada speed_interval_s.
    - El tipo de vehículo se decide por votación (no salta entre auto y camión).
    - Si la IA pierde un vehículo un instante, se sigue mostrando lost_visible_s en
      su posición prevista (sin parpadeo).
    - Si el seguidor da una ID nueva a un vehículo recién perdido, se reengancha al
      vehículo anterior: no aparece duplicado ni se cuenta dos veces.
    """

    def __init__(self, calibrator):
        """Prepara el seguidor sin vehículos ni conteos, usando el calibrador indicado."""
        self.calibrator = calibrator
        self.vehicles = {}
        self.total_counted = 0
        self.counts_by_class = {cls_name: 0 for cls_name in COUNT_CLASSES}
        self.new_crossings = []
        self.reload()

    def reload(self):
        """Lee los parámetros de vision.conf [tracking]."""
        t = AppConfig.get_instance().section("vision", "tracking")
        self.min_hits = int(t.get("min_hits", 3))
        self.smoothing_window = max(0.1, float(t.get("smoothing_window_s", 0.5)))
        self.motion_smoothing = max(0.0, float(t.get("motion_smoothing_s", 0.15)))
        self.forget_s = float(t.get("forget_s", 1.0))
        self.lost_visible_s = min(self.forget_s, float(t.get("lost_visible_s", 0.5)))
        self.interval_speed = max(0.2, float(t.get("speed_interval_s", 1.0)))
        self.speed_window = max(0.3, float(t.get("speed_window_s", 1.0)))
        self.stopped_threshold = float(t.get("stopped_speed_kmh", 5))

    def reset_count(self):
        """Pone en cero los totales y permite volver a contar los vehículos presentes."""
        self.total_counted = 0
        self.counts_by_class = {cls_name: 0 for cls_name in COUNT_CLASSES}
        for v in self.vehicles.values():
            v.counted_lines.clear()

    def visible(self, now=None):
        """Devuelve los vehículos confirmados que se ven ahora (sin objetos fijos)."""
        now = time.time() if now is None else now
        return [v for v in self.vehicles.values()
                if v.hits >= self.min_hits and not v.hidden and now - v.last_seen <= self.lost_visible_s]

    def stopped(self, now=None):
        """Cuenta los vehículos visibles prácticamente quietos (cola en el semáforo)."""
        return sum(1 for v in self.visible(now) if v.speed_kmh < self.stopped_threshold)

    def snapshot(self, now):
        """Devuelve los vehículos a dibujar en el instante now, con la caja prevista."""
        return [
            VehicleView(v.track_id, v.class_name, v.predicted_box(now), v.speed_kmh, v.counted,
                          list(v.trajectory)[-30:])
            for v in self.visible(now)
        ]

    def update_tracks(self, detections, lines, width, height, now=None):
        """Actualiza los vehículos con las detecciones de un cuadro y revisa los cruces.

        detections: [{'id', 'class', 'bbox', 'conf'}]; lines: [CountLine];
        now: instante en que se capturo el cuadro analizado.
        """
        now = time.time() if now is None else now
        self.new_crossings = []
        seen = set()

        # Actualiza o crea cada vehículo detectado
        current_ids = {det["id"] for det in detections}
        for det in detections:
            t_id = det["id"]
            seen.add(t_id)
            v = self.vehicles.get(t_id)
            if v is None:
                v = self._reattach(t_id, det["bbox"], current_ids, now)
            if v is None:
                v = TrackedVehicle(t_id, det["class"], det["bbox"], det["conf"], now,
                                   self.smoothing_window, self.motion_smoothing)
                self.vehicles[t_id] = v
                continue

            v.update_state(det["bbox"], det["conf"], det["class"], now)
            v.measure_speed(self.calibrator, now, self.speed_window, self.interval_speed)
            if not v.hidden:
                self.calibrator.observe(v.class_name, det["bbox"], det["conf"])
            self._check_lines(v, lines, width, height, now)

        # Olvida los vehículos que no se ven desde hace más de forget_s
        for t_id in [i for i, v in self.vehicles.items() if i not in seen and now - v.last_seen > self.forget_s]:
            del self.vehicles[t_id]
        return list(self.vehicles.values())

    def _check_lines(self, v, lines, width, height, now):
        """Cuenta el cruce cuando el punto de apoyo pasa de un lado de la línea al otro.

        Se recuerda el último punto que estuvo claramente a un lado, así un vehículo
        que queda justo sobre la línea en un cuadro también se cuenta.
        """
        for line in lines:
            a, b = line.to_pixels(width, height)
            value = side(v.anchor, a, b)
            if abs(value) < 1e-6:
                continue
            sign = 1 if value > 0 else -1
            previous = v.sides.get(line.id)
            v.sides[line.id] = (sign, v.anchor)
            if previous is None or previous[0] == sign or line.id in v.counted_lines:
                continue
            if v.hits < self.min_hits or v.hidden:
                continue
            direction = crosses_segment(previous[1], v.anchor, a, b)
            if direction:
                self._record_crossing(v, line, direction, now)

    def _reattach(self, new_id, box, current_ids, now):
        """Busca un vehículo perdido hace poco en el mismo lugar y le asigna la ID nueva."""
        best, value = None, IOU_REATTACH
        for v in self.vehicles.values():
            if v.track_id in current_ids or not 0 < now - v.last_seen <= self.forget_s:
                continue
            similarity = iou(v.predicted_box(now), box)
            if similarity > value:
                best, value = v, similarity
        if best is not None:
            del self.vehicles[best.track_id]
            best.track_id = new_id
            self.vehicles[new_id] = best
        return best

    def _record_crossing(self, v, line, direction, now):
        """Suma el cruce a la línea y a los totales, y agrega el evento a new_crossings."""
        first_time = not v.counted_lines
        v.counted_lines.add(line.id)
        if direction > 0:
            line.pos_count += 1
        else:
            line.neg_count += 1
        if first_time:  # los totales cuentan cada vehículo una sola vez
            self.total_counted += 1
            key = v.class_name.lower()
            self.counts_by_class[key if key in self.counts_by_class else "other"] += 1
        evt = {
            "timestamp": now,
            "track_id": v.track_id,
            "class": v.class_name,
            "speed_kmh": round(v.speed_kmh, 1),
            "line": line.id,
            "direction": direction,
            "new_vehicle": first_time,
        }
        self.new_crossings.append(evt)
