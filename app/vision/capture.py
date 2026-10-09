import logging
import threading
import time
from pathlib import Path

import cv2

from ..core.app_config import AppConfig
from .camera_enumerator import open_camera

_log = logging.getLogger(__name__)


# --- Fuente de video ---

class VideoSource:
    """Fuente de video: cámara USB, cámara IP (RTSP/HTTP) o archivo, según camera.conf.

    Si no hay señal no se inventa video: la interfaz muestra un aviso con un botón
    para configurar la cámara y aquí se reintenta abrirla cada retry_s.
    """

    def __init__(self, notify=None):
        """Prepara la fuente sin captura abierta y lee los parámetros de camera.conf."""
        self._notify = notify or (lambda text: None)
        self.cap = None
        self.name = "Sin cámara"
        self.source_fps = 30.0
        self._next_attempt = 0.0
        self._no_signal_warned = False
        self.reload()

    def reload(self):
        """Lee el tipo de fuente, la resolución, los FPS y el tiempo de reintento de camera.conf."""
        cfg = AppConfig.get_instance()
        self.kind = str(cfg.get("camera", "source_type", default="usb")).lower()
        self.index = int(cfg.get("camera", "device_index", default=0))
        self.device_name = cfg.get_text("camera", "device_name", "")
        self.stream_url = cfg.get_text("camera", "stream_url", "")
        self.file = cfg.get_text("camera", "video_file", "")
        self.width = cfg.get("camera", "width", default=1280)
        self.height = cfg.get("camera", "height", default=720)
        self.fps = max(1, int(cfg.get("camera", "fps", default=30)))
        self.retry_s = max(1.0, float(cfg.get("camera", "retry_s", default=5)))

    def signature(self):
        """Identifica la fuente; si cambia hay que reabrir la captura."""
        return (self.kind, self.index, self.stream_url, self.file)

    @property
    def connected(self):
        """Indica si hay una captura abierta."""
        return self.cap is not None

    # --- Apertura y lectura ---

    def open_source(self):
        """Abre la fuente configurada; devuelve True si lo logra o registra la falta de señal."""
        self.close()
        self._next_attempt = time.time() + self.retry_s
        try:
            # Apertura según el tipo de fuente
            if self.kind == "stream":
                if not self.stream_url:
                    return self._no_signal("No hay URL de cámara IP configurada.")
                cap = cv2.VideoCapture(self.stream_url)
                name = "Cámara IP"
            elif self.kind == "file":
                if not self.file or not Path(self.file).exists():
                    return self._no_signal("El archivo de video configurado no existe.")
                cap = cv2.VideoCapture(self.file)
                name = Path(self.file).name
            else:
                cap, backend = open_camera(self.index)
                name = self.device_name or f"Cámara {self.index}"
                if backend:
                    name = f"{name} ({backend})"

            if cap is None or not cap.isOpened():
                return self._no_signal("No se pudo abrir la cámara configurada.")

            # Resolución y FPS pedidos a la cámara; se usan los FPS reales si son validos
            if self.kind != "file":
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.fps)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # siempre el cuadro más nuevo
            fps_real = cap.get(cv2.CAP_PROP_FPS) or 0
            self.source_fps = fps_real if 1 <= fps_real <= 240 else float(self.fps)
            self.cap = cap
            self.name = name
            self._no_signal_warned = False
            self._notify(f"Video conectado: {name}.")
            return True
        except Exception as error:
            _log.exception("Error al abrir la fuente de video")
            return self._no_signal(f"Error al abrir la cámara: {error}")

    def _no_signal(self, reason):
        """Marca la fuente sin señal, avisa una sola vez y devuelve False."""
        self.cap = None
        self.name = "Sin cámara"
        if not self._no_signal_warned:  # avisar una sola vez, no en cada reintento
            self._notify(f"{reason} Reintentando cada {self.retry_s:.0f} s.")
            self._no_signal_warned = True
        return False

    def read_frame(self):
        """Devuelve el siguiente cuadro BGR, o None si no hay señal (reintenta abrir periodicamente)."""
        if self.cap is None:
            if time.time() >= self._next_attempt:
                self.open_source()
            return None

        ok, frame = self.cap.read()
        if ok and frame is not None:
            return frame
        if self.kind == "file":
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # reproducir en bucle
            ok, frame = self.cap.read()
            if ok:
                return frame
        # Perdida de señal: se cierra y se programa el siguiente reintento
        self.close()
        self._no_signal("Se perdió la señal de video.")
        self._next_attempt = time.time() + self.retry_s
        return None

    def close(self):
        """Libera la captura si esta abierta."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None


# --- Lector continuo ---

class FrameReader(threading.Thread):
    """Hilo que lee la fuente sin parar y deja disponible el último cuadro.

    Guarda solo el cuadro más reciente: la IA y la pantalla nunca esperan a la
    cámara ni procesan cuadros atrasados (sin retraso acumulado).
    """

    def __init__(self, source):
        """Prepara el hilo sobre la fuente indicada, sin cuadros todavía."""
        super().__init__(daemon=True, name="capture")
        self.source = source
        self._condition = threading.Condition()
        self._frame = None
        self._instant = 0.0
        self.seq = 0
        self.has_signal = False
        self._active = True
        self._reopen = False

    def reopen(self):
        """Pide recargar la configuración y reabrir la fuente en el siguiente ciclo."""
        self._reopen = True

    def shutdown(self):
        """Detiene el ciclo y despierta a quien espera un cuadro."""
        self._active = False
        with self._condition:
            self._condition.notify_all()

    def wait_new(self, seen_seq, max_wait=0.5):
        """Bloquea hasta que llegue un cuadro más nuevo que seen_seq y devuelve (cuadro, instante, seq)."""
        with self._condition:
            if self.seq == seen_seq and self._active:
                self._condition.wait(max_wait)
            return self._frame, self._instant, self.seq

    def run(self):
        """Lee cuadros hasta que se detiene, reabriendo la fuente cuando se pide."""
        self.source.open_source()
        next_at = time.time()
        while self._active:
            if self._reopen:
                self._reopen = False
                self.source.reload()
                self.source.open_source()
            # Publica el cuadro nuevo y avisa a los que esperan
            frame = self.source.read_frame()
            now = time.time()
            with self._condition:
                self.has_signal = frame is not None
                if frame is not None:
                    self._frame, self._instant = frame, now
                    self.seq += 1
                    self._condition.notify_all()
            if frame is None:
                time.sleep(0.25)
                continue
            if self.source.kind == "file":   # los archivos se leen a su velocidad real
                next_at = max(next_at + 1.0 / self.source.source_fps, now - 0.5)
                wait = next_at - time.time()
                if wait > 0:
                    time.sleep(wait)
        self.source.close()
