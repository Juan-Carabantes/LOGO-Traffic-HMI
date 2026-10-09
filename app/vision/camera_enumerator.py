import logging
import os

# Oculta los avisos internos de OpenCV al probar backends que no aplican
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2

_log = logging.getLogger(__name__)

_BACKENDS = {
    "dshow": getattr(cv2, "CAP_DSHOW", 700),
    "msmf": getattr(cv2, "CAP_MSMF", 1400),
    "any": getattr(cv2, "CAP_ANY", 0),
}

try:
    from pygrabber.dshow_graph import FilterGraph
    PYGRABBER_AVAILABLE = True
except Exception:
    PYGRABBER_AVAILABLE = False


# --- Apertura de cámaras ---

def backend_order():
    """Devuelve el orden de backends a probar según camera.conf backends (p. ej. dshow, msmf, any)."""
    from ..core.app_config import AppConfig

    text = AppConfig.get_instance().get_text("camera", "backends", "dshow, msmf, any")
    names = [n.strip().lower() for n in text.split(",") if n.strip()]
    return [(n, _BACKENDS[n]) for n in names if n in _BACKENDS] or [("any", _BACKENDS["any"])]


def open_camera(index):
    """Abre una cámara por índice probando cada backend hasta que uno funcione.

    Devuelve (captura, nombre del backend) o (None, None) si ninguno la pudo abrir.
    """
    for name, backend in backend_order():
        try:
            cap = cv2.VideoCapture(int(index), backend)
            if cap is not None and cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    return cap, name
            if cap is not None:
                cap.release()
        except Exception as error:
            _log.debug("Backend %s fallo con la cámara %s: %s", name, index, error)
    return None, None


# --- Enumeración de dispositivos ---

def list_camera_devices(max_indexes=None):
    """Devuelve una lista de tuplas (índice, nombre real) de las cámaras detectadas."""
    devices = []
    # Nombres reales de los dispositivos DirectShow
    if PYGRABBER_AVAILABLE:
        try:
            graph = FilterGraph()
            device_names = graph.get_input_devices()
            for idx, name in enumerate(device_names):
                devices.append((idx, str(name)))
        except Exception:
            devices = []

    # Si pygrabber no devuelve nada o falla, se hace un barrido rápido con OpenCV
    if not devices:
        if max_indexes is None:
            from ..core.app_config import AppConfig
            max_indexes = AppConfig.get_instance().get("camera", "max_search_indexes", default=4)
        for idx in range(int(max_indexes)):
            cap, _ = open_camera(idx)
            if cap is not None:
                devices.append((idx, f"Cámara USB #{idx} (Genérica)"))
                cap.release()

    return devices
