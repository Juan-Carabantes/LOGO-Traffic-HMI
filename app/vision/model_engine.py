import importlib.util
import logging
import shutil
from pathlib import Path

from ..core.app_config import BUNDLED_MODELS_DIR, PROJECT_DIR
from ..core.settings import MODELS_DIR

_log = logging.getLogger(__name__)
FALLBACK_MODELS = ("yolo11n.pt", "yolov8n.pt")


# --- Utilidades ---

def openvino_available():
    """Indica si el paquete openvino se puede importar."""
    return importlib.util.find_spec("openvino") is not None


def rect_size(imgsz, width, height, step=32):
    """Calcula la resolución de análisis con la proporción del video: 640 en 1280x720 -> (384, 640)."""
    side = int(imgsz)
    if width >= height:
        w, h = side, side * height / max(1, width)
    else:
        h, w = side, side * width / max(1, height)
    round_up = lambda v: max(step, int(-(-v // step) * step))  # hacia arriba al multiplo de 32
    return round_up(h), round_up(w)


def weights_path(name):
    """Busca el .pt en models/, en los modelos incluidos en el .exe y en la raiz; si no existe, la ruta en models/."""
    name = Path(str(name)).name
    for folder in (MODELS_DIR, BUNDLED_MODELS_DIR, PROJECT_DIR):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return MODELS_DIR / name


# --- Carga por motor ---

def _load_pytorch(name):
    """Carga el modelo .pt, o uno de FALLBACK_MODELS si falla; devuelve (modelo, nombre corto).

    Los pesos que no están en disco se descargan a models/ la primera vez (requiere internet).
    """
    from ultralytics import YOLO

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for candidate in (name, *FALLBACK_MODELS):
        try:
            path = weights_path(candidate)
            model = YOLO(str(path))
            if candidate != name:
                _log.warning("No se pudo usar %s; se usa %s.", name, candidate)
            return model, Path(candidate).stem
        except Exception as error:
            _log.warning("No se pudo cargar el modelo %s: %s", candidate, error)
    return None, ""


def _load_openvino(name, size, notify):
    """Carga el modelo en formato OpenVINO; devuelve (modelo, nombre corto).

    La primera vez el modelo se exporta desde el .pt (unos segundos) y se guarda en
    models/<modelo>_<alto>x<ancho>_openvino_model/ para las siguientes veces.
    """
    from ultralytics import YOLO

    height, width = size
    stem = Path(name).stem
    folder = lambda model_name: MODELS_DIR / f"{model_name}_{height}x{width}_openvino_model"
    target = folder(stem)
    # Versión ya optimizada incluida en el .exe: se usa directamente
    bundled = BUNDLED_MODELS_DIR / target.name
    if not (target / f"{stem}.xml").exists() and (bundled / f"{stem}.xml").exists():
        return YOLO(str(bundled), task="detect"), stem
    # Exportación única cuando aún no existe la carpeta del modelo convertido
    if not (target / f"{stem}.xml").exists():
        notify(f"Optimizando {stem} para esta CPU (OpenVINO, solo la primera vez)…")
        model_pt, stem_real = _load_pytorch(name)
        if model_pt is None:
            return None, ""
        stem = stem_real
        target = folder(stem)
        if not (target / f"{stem}.xml").exists():
            exported = Path(model_pt.export(format="openvino", imgsz=[height, width], dynamic=False, verbose=False))
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(exported), str(target))
            _log.info("Modelo OpenVINO guardado en %s", target)
    return YOLO(str(target), task="detect"), stem


def load_model(name, size, engine="auto", notify=None):
    """Carga el modelo YOLO con el motor de vision.conf [detection] engine.

    Motores: "auto" usa OpenVINO si esta disponible y si no PyTorch; "openvino"
    acelera la CPU (Intel y AMD) unas 3 veces; "pytorch" usa el .pt tal cual (con
    la GPU NVIDIA si el perfil lo pide). Devuelve (modelo, nombre corto, motor usado);
    el modelo es None si nada funciono.
    """
    notify = notify or (lambda text: None)
    engine = str(engine or "auto").lower()
    if engine in ("auto", "openvino"):
        if openvino_available():
            try:
                model, stem = _load_openvino(name, size, notify)
                if model is not None:
                    return model, stem, "openvino"
            except Exception as error:
                _log.warning("OpenVINO no disponible para %s (%s); se usa PyTorch.", name, error)
        elif engine == "openvino":
            notify("OpenVINO no está instalado (pip install openvino); se usa PyTorch.")
    model, stem = _load_pytorch(name)
    return model, stem, "pytorch"
