import logging
import time
from datetime import datetime

import cv2

from ..core.app_config import AppConfig
from ..core.settings import RECORDINGS_DIR

_log = logging.getLogger(__name__)


class VideoRecorder:
    """Graba el video procesado a MP4 con los parámetros de camera.conf [recording]."""

    def __init__(self):
        """Prepara el grabador detenido y sin archivo."""
        self.writer = None
        self.path = ""
        self.start = 0.0
        self.active = False

    @property
    def duration(self):
        """Devuelve los segundos transcurridos desde que empezó la grabación, o 0 si no graba."""
        return time.time() - self.start if self.active else 0.0

    def start_recording(self):
        """Crea la carpeta y el nombre del archivo con fecha y hora, y activa la grabación."""
        cfg = AppConfig.get_instance()
        folder = cfg.path("camera", "recordings_dir") or RECORDINGS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        prefix = cfg.get_text("camera", "file_prefix", "traffic")
        self.path = str(folder / f"{prefix}_{datetime.now():%Y-%m-%d_%H-%M-%S}.mp4")
        self.writer = None  # se crea con el tamaño del primer cuadro
        self.start = time.time()
        self.active = True
        _log.info("Grabación iniciada: %s", self.path)
        return self.path

    def write(self, frame, fps=None):
        """Escribe un cuadro; fps son los cuadros por segundo reales de la pantalla.

        Usar los FPS reales hace que el video dure lo mismo que la grabación.
        """
        if not self.active:
            return
        # El escritor se crea con el primer cuadro, cuando ya se conoce su tamaño
        if self.writer is None:
            cfg = AppConfig.get_instance()
            codec = cfg.get_text("camera", "codec", "mp4v")[:4].ljust(4)
            fps = float(fps or cfg.get("camera", "recording_fps", default=25))
            height, width = frame.shape[:2]
            self.writer = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*codec), round(fps, 1), (width, height))
        self.writer.write(frame)

    def shutdown(self):
        """Cierra el archivo y detiene la grabación."""
        if self.writer is not None:
            try:
                self.writer.release()
            except Exception:
                pass
        if self.active:
            _log.info("Grabación detenida: %s", self.path)
        self.writer = None
        self.active = False
