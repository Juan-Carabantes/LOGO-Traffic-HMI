import importlib.util
import logging
import time
import warnings

from ..core.app_config import AppConfig
from ..core.hardware_detector import get_profile_settings
from ..core.settings import DATA_DIR
from .geometry import box_area, intersection, iou
from .model_engine import load_model, rect_size

warnings.filterwarnings("ignore", message=".*not enough matching points.*")

YOLO_AVAILABLE = importlib.util.find_spec("ultralytics") is not None

_log = logging.getLogger(__name__)

# Clases COCO de vehículos, nombres visibles y claves del umbral en vision.conf
COCO_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
CLASS_LABELS = {"car": "Auto", "motorcycle": "Moto", "bus": "Autobús", "truck": "Camión"}
_THRESHOLD_KEY = {"car": "car_confidence", "motorcycle": "motorcycle_confidence",
                  "bus": "bus_confidence", "truck": "truck_confidence"}
_DEFAULT_THRESHOLD = {"car": 0.40, "motorcycle": 0.25, "bus": 0.45, "truck": 0.45}
CONFIRMED_FORGET_S = 5.0


# --- Duplicados ---

def _overlap(c1, c2):
    """Devuelve el mayor entre el IoU y la fracción de la caja pequeña cubierta por la grande."""
    smaller = min(box_area(c1), box_area(c2))
    content = intersection(c1, c2) / smaller if smaller > 0 else 0.0
    return max(iou(c1, c2), content)


def remove_duplicates(detections, iou_threshold, contain_threshold):
    """Deja una sola caja por vehículo (la de mayor confianza).

    Entre una moto y un auto o camión solo se usa el IoU: en perspectiva una moto
    puede quedar dentro de la caja de un camión que va al lado.
    """
    final = []
    for det in sorted(detections, key=lambda d: d["conf"], reverse=True):
        duplicate = False
        for other in final:
            iou_value = iou(det["bbox"], other["bbox"])
            if (det["class"] == "motorcycle") != (other["class"] == "motorcycle"):
                duplicate = iou_value > iou_threshold
            else:
                duplicate = iou_value > iou_threshold or _overlap(det["bbox"], other["bbox"]) > contain_threshold
            if duplicate:
                break
        if not duplicate:
            final.append(det)
    return final


# --- Detector de vehículos ---

class VehicleDetector:
    """Detecta y sigue vehículos con YOLO usando vision.conf [detection], [tracker_tuning] y [profile_*].

    Para detectar mejor: usa modelos YOLO26 (mejores con objetos pequeños como motos)
    y el motor OpenVINO en CPU (ver model_engine.py); analiza con la proporción del
    video (640x384 en lugar de 640x640); aplica una confianza mínima por tipo, porque
    las motos puntúan más bajo que los autos (un vehículo se muestra cuando alguna vez
    supera el umbral de su tipo y después el seguidor lo mantiene aunque baje un poco);
    envía al seguidor también las detecciones débiles para no perder vehículos entre
    cuadros (menos parpadeo y menos IDs nuevos); elimina cajas duplicadas aunque sean
    de distinta clase o una este dentro de otra; y descarta cajas diminutas o fuera de
    la zona de detección.
    """

    def __init__(self, profile_name="medium", notify=None):
        """Prepara el detector sin modelo cargado y aplica los parámetros y el perfil indicado."""
        self._notify = notify or (lambda text: None)
        self.model = None
        self.model_name = ""
        self.engine = ""
        self.size = None               # (alto, ancho) de análisis
        self._frame_size = None
        self._reload_model = True
        self.zone = None               # DetectionZone (la asigna el hilo de video)
        self._confirmed = {}           # id -> última vez visto confirmado
        self.analyzed = False          # True si el último cuadro se analizó sin errores
        self._error_warned = False
        self.reload_params()
        self.set_profile(profile_name)

    # --- Configuración ---

    def reload_params(self):
        """Lee los umbrales de detección y los parámetros del seguidor de vision.conf."""
        cfg = AppConfig.get_instance()
        d = cfg.section("vision", "detection")
        self.requested_engine = str(d.get("engine", "auto")).lower()
        self.iou = float(d.get("iou_nms", 0.5))
        self.content = float(d.get("contain_overlap", 0.8))
        self.merge_classes = bool(d.get("class_agnostic_nms", True))
        self.min_area = float(d.get("min_area_pct", 0.03)) / 100.0
        self.thresholds = {cls_name: float(d.get(key, _DEFAULT_THRESHOLD[cls_name])) for cls_name, key in _THRESHOLD_KEY.items()}

        # Parámetros del seguidor; si cambian se regenera su .yaml y se recarga el modelo
        s = cfg.section("vision", "tracker_tuning")
        tracker = {
            "kind": str(d.get("tracker", "bytetrack.yaml")),
            "track_high_thresh": float(s.get("high_thresh", 0.25)),
            "track_low_thresh": float(s.get("low_thresh", 0.1)),
            "new_track_thresh": float(s.get("new_thresh", 0.25)),
            "track_buffer": int(s.get("buffer_frames", 45)),
            "match_thresh": float(s.get("match_thresh", 0.8)),
            "gmc": bool(s.get("camera_motion_comp", False)),
        }
        if tracker != getattr(self, "_tracker", None):
            self._tracker = tracker
            self.tracker_file = self._write_tracker(tracker)
            self._reload_model = True   # el seguidor se crea junto con el modelo

    def _write_tracker(self, s):
        """Genera el .yaml del seguidor a partir del de ultralytics con los valores de vision.conf."""
        if not YOLO_AVAILABLE:
            return s["kind"]
        try:
            import yaml
            from ultralytics.utils.checks import check_yaml

            with open(check_yaml(s["kind"]), encoding="utf-8") as file:
                base = yaml.safe_load(file)
            for key in ("track_high_thresh", "track_low_thresh", "new_track_thresh", "track_buffer", "match_thresh"):
                base[key] = s[key]
            if "gmc_method" in base and not s["gmc"]:
                base["gmc_method"] = "none"   # cámara fija: no hace falta y consume CPU
            # Se guarda en DATA_DIR/cache para no modificar el archivo de ultralytics
            folder = DATA_DIR / "cache"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"tracker_{base.get('tracker_type', 'bytetrack')}.yaml"
            with open(path, "w", encoding="utf-8") as file:
                yaml.safe_dump(base, file, allow_unicode=True, sort_keys=False)
            return str(path)
        except Exception as error:
            _log.warning("No se pudo preparar el seguidor (%s); se usa %s.", error, s["kind"])
            return s["kind"]

    def set_profile(self, profile_name):
        """Aplica un perfil de rendimiento y marca el modelo para recargar si cambio el modelo, imgsz o device."""
        self.profile_name = profile_name
        profile = get_profile_settings(profile_name)
        key = (profile.get("model"), profile.get("imgsz"), profile.get("device"))
        if key != getattr(self, "_profile_key", None):
            self._profile_key = key
            self._reload_model = True
        self.profile = profile

    def threshold(self, cls_name):
        """Devuelve la confianza mínima configurada para el tipo de vehículo."""
        return self.thresholds.get(cls_name, 0.4)

    @property
    def min_confidence(self):
        """Devuelve la confianza mínima enviada al seguidor, que recibe también las detecciones débiles."""
        return max(0.05, min(self._tracker["track_low_thresh"], min(self.thresholds.values())))

    @property
    def description(self):
        """Devuelve un texto con el modelo, el motor y la resolución de análisis."""
        if self.model is None:
            return "cargando…" if YOLO_AVAILABLE else "sin IA (instala ultralytics)"
        height, width = self.size
        engine = "OpenVINO" if self.engine == "openvino" else ("GPU" if self.profile.get("device") != "cpu" else "CPU")
        return f"{self.model_name} · {engine} · {width}x{height}"

    # --- Modelo ---

    def _prepare(self, width, height):
        """Carga el modelo si hace falta o si cambio el tamaño del cuadro."""
        if not YOLO_AVAILABLE:
            return
        if not self._reload_model and self._frame_size == (width, height):
            return
        self._reload_model = False
        self._frame_size = (width, height)
        # Con GPU se usa PyTorch; en CPU, el motor pedido en vision.conf
        self.size = rect_size(self.profile.get("imgsz", 640), width, height)
        engine = "pytorch" if self.profile.get("device") != "cpu" else self.requested_engine
        start = time.time()
        self.model, self.model_name, self.engine = load_model(
            self.profile.get("model", "yolo26n.pt"), self.size, engine, self._notify)
        self._confirmed.clear()
        if self.model is None:
            self._notify("No se pudo cargar ningún modelo de detección.")
        else:
            _log.info("Modelo listo en %.1f s: %s", time.time() - start, self.description)

    # --- Detección ---

    def detect_and_track(self, frame):
        """Detecta y sigue vehículos; devuelve [{'id', 'class', 'bbox': [x1,y1,x2,y2], 'conf'}] ya filtradas."""
        self.analyzed = False
        if frame is None:
            return []
        height, width = frame.shape[:2]
        self._prepare(width, height)
        if self.model is None:
            return []

        # Inferencia y seguimiento; el error se registra una sola vez
        device = self.profile.get("device", "cpu")
        try:
            results = self.model.track(
                source=frame,
                persist=True,
                tracker=self.tracker_file,
                classes=list(COCO_VEHICLE_CLASSES),
                conf=self.min_confidence,
                iou=self.iou,
                imgsz=list(self.size),
                max_det=int(self.profile.get("max_det", 60)),
                agnostic_nms=self.merge_classes,
                device=device if self.engine == "pytorch" else "cpu",
                verbose=False,
            )
        except Exception as error:
            if not self._error_warned:
                _log.error("Error en la inferencia: %s", error)
                self._error_warned = True
            self.analyzed = False
            return []
        self.analyzed = True
        self._error_warned = False

        boxes = results[0].boxes if results and results[0].boxes is not None else None
        if boxes is None or boxes.id is None:
            return []
        return self.filter_boxes(
            boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), boxes.id.tolist(), width, height)

    def filter_boxes(self, xyxy, confs, classes, ids, width, height, now=None):
        """Aplica tamaño mínimo, zona, duplicados y umbral por tipo (separado para poder probarlo)."""
        now = time.time() if now is None else now
        frame_area = float(width * height)
        # Tamaño mínimo y zona: se usa el punto de apoyo (centro inferior de la caja)
        candidates = []
        for box, conf, cls, track_id in zip(xyxy, confs, classes, ids):
            cls_name = COCO_VEHICLE_CLASSES.get(int(cls))
            if cls_name is None or box_area(box) < self.min_area * frame_area:
                continue
            anchor = ((box[0] + box[2]) / 2.0, box[3])
            if self.zone is not None and not self.zone.contains(anchor, width, height):
                continue
            candidates.append({"id": int(track_id), "class": cls_name, "conf": float(conf),
                               "bbox": [float(v) for v in box]})

        if self.merge_classes:
            candidates = remove_duplicates(candidates, self.iou, self.content)

        # Umbral por tipo: un ID que ya lo supero se mantiene durante CONFIRMED_FORGET_S
        detections = []
        for det in candidates:
            if det["conf"] >= self.threshold(det["class"]) or det["id"] in self._confirmed:
                self._confirmed[det["id"]] = now
                detections.append(det)
        for track_id in [i for i, t in self._confirmed.items() if now - t > CONFIRMED_FORGET_S]:
            del self._confirmed[track_id]
        return detections
