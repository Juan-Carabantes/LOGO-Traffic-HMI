import copy
import logging
import math
import threading
import time
from collections import deque

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from ..analytics.traffic_analyzer import TrafficAnalyzer
from ..core.app_config import AppConfig
from ..core.hardware_detector import update_interval_ms
from .calibration import SpatialCalibrator
from .capture import VideoSource, FrameReader
from .counting_lines import load_lines, save_lines
from .detector import VehicleDetector
from .overlay import OverlayRenderer
from .recorder import VideoRecorder
from .static_filter import FixedObjectFilter
from .tracker import VehicleTracker
from .zone import load_zone, save_zone

_log = logging.getLogger(__name__)
CALIBRATION_SAVE_S = 60


# --- Medidor de FPS ---

class _RateMeter:
    """Mide los cuadros por segundo de los últimos ~2 s."""

    def __init__(self):
        """Prepara el medidor sin marcas."""
        self._times = deque(maxlen=120)

    def mark(self, t=None):
        """Registra un cuadro en el instante indicado o en el actual."""
        self._times.append(time.time() if t is None else t)

    def value(self):
        """Devuelve los FPS de las marcas de los últimos 2 s, o 0 si no hay suficientes."""
        now = time.time()
        recent = [t for t in self._times if now - t <= 2.0]
        if len(recent) < 2:
            return 0.0
        return (len(recent) - 1) / max(1e-3, recent[-1] - recent[0])


# --- Hilo de video ---

class VideoWorker(QThread):
    """Procesa el video en tres hilos que trabajan en paralelo.

    Captura (FrameReader) lee la cámara sin parar y deja el último cuadro; IA
    (_ai_loop) aplica YOLO, seguimiento y conteo sobre el cuadro más nuevo; pantalla
    (run, este QThread) dibuja y envía cada cuadro a la interfaz y a la grabación.
    Así el video se ve fluido a la velocidad de la cámara (hasta max_screen_fps)
    aunque la IA analice menos cuadros por segundo: las cajas se dibujan en su
    posición prevista entre un análisis y el siguiente.
    """

    frame_ready = pyqtSignal(QImage, int, int)    # imagen, ancho, alto
    stats_updated = pyqtSignal(dict)              # metricas de tráfico (cada update_interval)
    recording_changed = pyqtSignal(bool, str)     # grabando, ruta
    error_occurred = pyqtSignal(str)              # avisos para la bitácora
    signal_changed = pyqtSignal(bool)             # True = hay video, False = sin cámara
    crossings_detected = pyqtSignal(list)         # eventos de cruce (para el historial)

    def __init__(self, parent=None):
        """Crea las etapas de captura, detección, seguimiento, análisis, dibujo y grabación."""
        super().__init__(parent)
        self.cfg = AppConfig.get_instance()
        self._active = True
        self._lock = threading.RLock()
        # Banderas que la interfaz activa y los hilos atienden en su siguiente vuelta
        self._reload_display = False
        self._reload_ai = False
        self._toggle_recording = False
        self._reset_count = False
        self._has_signal = None
        self._pending_crossings = []
        self._editing_zone = False

        # Etapas del procesamiento
        self.calibrator = SpatialCalibrator()
        self.detector = VehicleDetector(self.cfg.get("vision", "profile", default="medium"),
                                        notify=self.error_occurred.emit)
        self.tracker = VehicleTracker(self.calibrator)
        self.fixed_filter = FixedObjectFilter()
        self.analyzer = TrafficAnalyzer()
        self.source = VideoSource(notify=self.error_occurred.emit)
        self.reader = FrameReader(self.source)
        self.overlay = OverlayRenderer()
        self.recorder = VideoRecorder()
        self.lines = load_lines()
        self.zone = load_zone()
        self.detector.zone = self.zone

        self.video_meter = _RateMeter()
        self.ai_meter = _RateMeter()
        self._last_cal_save = time.time()
        self._info_hud = {}
        self._configure()

    def _configure(self):
        """Lee el intervalo de estadísticas, los FPS máximos de pantalla y el filtro de objetos fijos."""
        cfg = self.cfg
        self.interval_stats = update_interval_ms() / 1000.0   # auto, tiempo real o segundos fijos
        self.max_fps = max(5, int(cfg.get("camera", "max_screen_fps", default=30)))
        z = cfg.section("vision", "zone")
        self.fixed_filter.configure(z.get("hide_fixed_objects", True), z.get("fixed_object_s", 45))

    # --- Llamadas desde la interfaz (hilo principal) ---

    def get_lines(self):
        """Devuelve una copia de las líneas de conteo."""
        with self._lock:
            return copy.deepcopy(self.lines)

    def set_lines(self, lines):
        """Reemplaza las líneas, conservando los conteos de las que ya existian."""
        with self._lock:
            prev_lines = {l.id: l for l in self.lines}
            for line in lines:
                if line.id in prev_lines:
                    line.pos_count = prev_lines[line.id].pos_count
                    line.neg_count = prev_lines[line.id].neg_count
            self.lines = copy.deepcopy(lines)

    def save_lines(self):
        """Guarda las líneas actuales en vision.conf."""
        save_lines(self.get_lines())

    def get_zone(self):
        """Devuelve una copia de la zona de detección."""
        with self._lock:
            return self.zone.copy_zone()

    def set_zone(self, zone, save=True):
        """Aplica una zona nueva al detector y, si se pide, la guarda en vision.conf."""
        with self._lock:
            self.zone = zone.copy_zone()
            self.detector.zone = self.zone
        if save:
            save_zone(zone)

    def set_zone_editing(self, editing):
        """Indica si se edita la zona; mientras tanto no se dibuja la guardada (la dibuja la interfaz)."""
        self._editing_zone = bool(editing)

    def forget_fixed_objects(self):
        """Borra las regiones de objetos fijos aprendidas."""
        with self._lock:
            self.fixed_filter.reset()

    def toggle_recording(self):
        """Pide iniciar o detener la grabación en la siguiente vuelta del hilo de pantalla."""
        self._toggle_recording = True

    def load_totals(self, totals):
        """Arranca los contadores desde el acumulado del historial ({total, by_class, lines})."""
        with self._lock:
            self.tracker.total_counted = int(totals.get("total", 0))
            for cls_name, count in totals.get("by_class", {}).items():
                key = cls_name if cls_name in self.tracker.counts_by_class else "other"
                self.tracker.counts_by_class[key] += int(count)
            for line in self.lines:
                line.pos_count, line.neg_count = totals.get("lines", {}).get(line.id, (0, 0))

    def reset_count(self):
        """Pide poner en cero los conteos en la siguiente vuelta del hilo de pantalla."""
        self._reset_count = True

    def reset_calibration(self):
        """Borra la escala aprendida (modo auto) en memoria y en vision.conf."""
        self.calibrator.reset_auto()
        for key in ("auto_a", "auto_b", "auto_samples"):
            self.cfg.set("vision", "calibration", key, 0)

    def update_settings(self):
        """Pide recargar la configuración; cada hilo la aplica en su siguiente vuelta."""
        self._reload_display = True
        self._reload_ai = True

    def stop(self):
        """Detiene los hilos, espera a que terminen y guarda la calibración."""
        self._active = False
        self.reader.shutdown()
        self.wait(4000)
        self._save_calibration()

    # --- Hilo de pantalla ---

    def run(self):
        """Arranca la captura y la IA, y dibuja cada cuadro nuevo hasta que se detiene."""
        self.reader.start()
        ai_thread = threading.Thread(target=self._ai_loop, name="ia", daemon=True)
        ai_thread.start()

        seen, next_at, last_stats = -1, 0.0, 0.0
        while self._active:
            # Espera un cuadro nuevo; sin señal se detiene la grabación
            self._pending_tasks()
            frame, instant, seq = self.reader.wait_new(seen)
            self._notify_signal(self.reader.has_signal)
            if not self.reader.has_signal:
                if self.recorder.active:
                    self._change_recording()
                continue
            if frame is None or seq == seen:
                continue
            seen = seq

            now = time.time()
            if now < next_at:               # limitar la pantalla a max_screen_fps
                continue
            period = 1.0 / self.max_fps
            next_at = max(next_at + period, now - period)
            try:
                self._show(frame.copy(), instant)
            except Exception:
                _log.exception("Error dibujando un cuadro de video")

            # Cruces, estadísticas y guardado periodico de la calibración
            self._emit_crossings()
            if now - last_stats >= self.interval_stats:
                last_stats = now
                self._publish_stats(frame.shape[1], frame.shape[0])
            if now - self._last_cal_save > CALIBRATION_SAVE_S:
                self._save_calibration()

        ai_thread.join(2.0)
        self.recorder.shutdown()

    def _pending_tasks(self):
        """Atiende las peticiones de la interfaz: recargar ajustes, grabar y reiniciar conteos."""
        # Recarga de ajustes; la fuente se reabre solo si cambio
        if self._reload_display:
            self._reload_display = False
            self.overlay.reload()
            self._configure()
            self.analyzer.reload_rules()
            signature = self.source.signature()
            self.source.reload()
            if self.source.signature() != signature:
                self.error_occurred.emit("Fuente de video cambiada; reabriendo…")
                self.reader.reopen()
        if self._toggle_recording:
            self._toggle_recording = False
            self._change_recording()
        if self._reset_count:
            self._reset_count = False
            with self._lock:
                self.tracker.reset_count()
                for line in self.lines:
                    line.pos_count = line.neg_count = 0

    def _notify_signal(self, has_signal):
        """Emite signal_changed solo cuando cambia el estado de la señal."""
        if has_signal != self._has_signal:
            self._has_signal = has_signal
            self.signal_changed.emit(has_signal)

    def _show(self, frame, instant):
        """Dibuja zona, plano, vehículos, líneas y panel, graba el cuadro y lo envía a la interfaz."""
        height, width = frame.shape[:2]
        self.video_meter.mark()
        with self._lock:
            vehicles = self.tracker.snapshot(instant)
            lines = self.lines
            zone = self.zone
            if not self._editing_zone:
                self.overlay.zone(frame, zone)
            self.overlay.draw_plane(frame, self.calibrator)
            self.overlay.vehicles(frame, vehicles)
            self.overlay.count_lines(frame, lines)
        self.overlay.panel_info(frame, self._info_hud)
        if self.recorder.active:
            self.overlay.rec_indicator(frame, self.recorder.duration)
            self.recorder.write(frame, self.video_meter.value() or self.max_fps)

        # Conversión a QImage; copy() evita depender del buffer de numpy
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
        self.frame_ready.emit(image, width, height)

    def _emit_crossings(self):
        """Envia los cruces acumulados por el hilo de IA."""
        with self._lock:
            crossings, self._pending_crossings = self._pending_crossings, []
        if crossings:
            self.crossings_detected.emit(crossings)

    # --- Hilo de IA ---

    def _ai_loop(self):
        """Analiza el cuadro más nuevo en bucle, recargando parámetros cuando se pide."""
        seen, previous = -1, None
        while self._active:
            if self._reload_ai:
                self._reload_ai = False
                self.detector.reload_params()
                self.detector.set_profile(self.cfg.get("vision", "profile", default="medium"))
                with self._lock:
                    self.calibrator.reload()
                    self.tracker.reload()
            frame, instant, seq = self.reader.wait_new(seen)
            if frame is None or seq == seen:
                continue
            seen = seq
            start = time.time()
            try:
                self._analyze(frame, instant, previous)
                previous = instant
            except Exception:
                _log.exception("Error analizando un cuadro de video")
                time.sleep(0.2)
            # Límite de análisis por segundo del perfil (ai_max_fps) para no saturar PCs basicas
            limit = float(self.detector.profile.get("ai_max_fps", 0) or 0)
            if limit > 0:
                time.sleep(max(0.0, 1.0 / limit - (time.time() - start)))

    def _analyze(self, frame, instant, previous):
        """Detecta, sigue y filtra los vehículos de un cuadro y registra los cruces nuevos."""
        height, width = frame.shape[:2]
        self.calibrator.set_frame_size(width, height)
        detections = self.detector.detect_and_track(frame)   # lo lento: fuera del candado
        if self.detector.analyzed:
            self.ai_meter.mark()
        else:
            time.sleep(0.05)
        dt = 0.0 if previous is None else min(1.0, instant - previous)
        with self._lock:
            vehicles = self.tracker.update_tracks(detections, self.lines, width, height, now=instant)
            self.fixed_filter.update_state(vehicles, dt, instant, math.hypot(width, height))
            crossings = list(self.tracker.new_crossings)
            self._pending_crossings.extend(crossings)
        # Al analizador solo llega la primera vez que cruza cada vehículo
        for evt in crossings:
            if evt["new_vehicle"]:
                self.analyzer.record_crossing(evt["timestamp"])

    # --- Estadísticas (cada update_interval de analytics.conf) ---

    def _publish_stats(self, width, height):
        """Actualiza los datos del panel y emite stats_updated con las metricas de tráfico."""
        del width, height
        now = time.time()
        with self._lock:
            visible = self.tracker.visible(now)
            stopped = self.tracker.stopped(now)
            lines = [{"id": l.id, "name": l.name, "total": l.total, "pos": l.pos_count, "neg": l.neg_count}
                      for l in self.lines]
            total = self.tracker.total_counted
            by_class = dict(self.tracker.counts_by_class)
            fixed = self.fixed_filter.fixed_count
        speeds = [v.speed_kmh for v in visible if v.speed_kmh > 0]
        speed = float(np.mean(speeds)) if speeds else 0.0
        in_scene = len(visible)
        fps_video, fps_ai = self.video_meter.value(), self.ai_meter.value()

        self._info_hud = {
            "source": self.source.name,
            "fps": fps_video,
            "fps_ai": fps_ai,
            "model": self.detector.description,
            "total": total,
            "in_scene": in_scene,
            "stopped": stopped,
            "calibration": self.calibrator.summary(),
        }
        self.stats_updated.emit({
            "total_counted": total,
            "count_by_class": by_class,
            "count_by_line": lines,
            "vehicles_in_scene": in_scene,
            "stopped": stopped,
            "fixed_objects": fixed,
            "flow_min": self.analyzer.get_flow_rate_per_minute(),
            "flow_hour": self.analyzer.get_projected_flow_per_hour(),
            "density_pct": self.analyzer.calculate_traffic_density(in_scene),
            "avg_speed": round(speed, 1),
            "timer_suggestions": self.analyzer.calculate_suggested_timers(in_scene, speed),
            "is_recording": self.recorder.active,
            "recording_duration": int(self.recorder.duration),
            "fps": round(fps_video, 1),
            "fps_ai": round(fps_ai, 1),
            "model": self.detector.description,
            "source": self.source.name,
            "calibration": self.calibrator.summary(),
            "calibration_ready": self.calibrator.ready,
        })

    # --- Grabación y calibración ---

    def _change_recording(self):
        """Inicia o detiene la grabación; sin señal de video avisa que no se puede grabar."""
        if self.recorder.active:
            self.recorder.shutdown()
            self.recording_changed.emit(False, "")
        elif self.source.connected:
            path = self.recorder.start_recording()
            self.recording_changed.emit(True, path)
        else:
            self.error_occurred.emit("No se puede grabar: no hay señal de video.")

    def _save_calibration(self):
        """Guarda la escala automática aprendida en vision.conf si ya esta lista."""
        self._last_cal_save = time.time()
        if self.calibrator.mode not in ("auto", "plane") or not self.calibrator.auto_ready:
            return
        a, b, n = self.calibrator.data_to_save()
        self.cfg.set("vision", "calibration", "auto_a", a)
        self.cfg.set("vision", "calibration", "auto_b", b)
        self.cfg.set("vision", "calibration", "auto_samples", n)
