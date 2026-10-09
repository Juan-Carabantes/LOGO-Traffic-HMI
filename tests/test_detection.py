from app.vision.calibration import SpatialCalibrator
from app.vision.detector import VehicleDetector, remove_duplicates
from app.vision.model_engine import rect_size
from app.vision.static_filter import FixedObjectFilter
from app.vision.tracker import VehicleTracker
from app.vision.zone import DetectionZone


def _det(tid, cls_name, box, conf):
    """Arma una detección con ID, clase, caja y confianza."""
    return {"id": tid, "class": cls_name, "bbox": box, "conf": conf}


def test_analysis_size_keeps_ratio():
    """Comprueba que el tamaño de análisis conserva la proporción del cuadro."""
    assert rect_size(640, 1280, 720) == (384, 640)
    assert rect_size(640, 720, 1280) == (640, 384)


def test_remove_duplicates():
    """Comprueba que se eliminan cajas duplicadas o contenidas sin perder la moto contigua."""
    auto = _det(1, "car", [100, 100, 300, 250], 0.8)
    truck = _det(2, "truck", [98, 95, 305, 255], 0.5)             # mismo vehículo, otra clase
    inner = _det(3, "car", [150, 150, 260, 240], 0.4)             # caja dentro de otra
    moto = _det(4, "motorcycle", [120, 180, 170, 250], 0.6)       # moto al lado (queda dentro en perspectiva)
    other = _det(5, "car", [500, 100, 700, 250], 0.7)
    ids = {d["id"] for d in remove_duplicates([auto, truck, inner, moto, other], 0.5, 0.8)}
    assert ids == {1, 4, 5}


def test_class_threshold_confirmation():
    """Comprueba los umbrales por clase y que un vehículo confirmado no parpadea."""
    det = VehicleDetector("medium")
    det.thresholds = {"car": 0.4, "motorcycle": 0.25, "bus": 0.45, "truck": 0.45}
    det.min_area = 0.0
    det._confirmed.clear()
    boxes = [[0, 0, 50, 80], [200, 0, 300, 80]]
    # La moto con 0.28 pasa; el auto con 0.30 todavía no
    output = det.filter_boxes(boxes, [0.28, 0.30], [3, 2], [1, 2], 1280, 720, now=0.0)
    assert [d["id"] for d in output] == [1]
    # El auto supera su umbral una vez...
    det.filter_boxes(boxes[1:], [0.55], [2], [2], 1280, 720, now=0.1)
    # ...y después se mantiene aunque la confianza baje (sin parpadeo)
    output = det.filter_boxes(boxes[1:], [0.2], [2], [2], 1280, 720, now=0.2)
    assert [d["id"] for d in output] == [2]


def test_zone_and_min_size():
    """Comprueba que se descartan cajas fuera de la zona o demasiado pequeñas."""
    det = VehicleDetector("medium")
    det.min_area = 0.001
    det.zone = DetectionZone(True, [[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]])   # mitad inferior
    boxes = [[100, 50, 300, 200],     # letrero arriba: fuera de la zona
             [100, 500, 300, 650],    # auto abajo: dentro
             [600, 600, 605, 604]]    # diminuta
    output = det.filter_boxes(boxes, [0.9, 0.9, 0.9], [2, 2, 2], [1, 2, 3], 1280, 720, now=0.0)
    assert [d["id"] for d in output] == [2]


def _tracker():
    """Crea un VehicleTracker con calibración por defecto y confirmación en 2 detecciones."""
    cal = SpatialCalibrator()
    cal.set_frame_size(1280, 720)
    t = VehicleTracker(cal)
    t.min_hits = 2
    return t


def test_still_sign_hidden_queue_car_not():
    """Comprueba que un letrero fijo se oculta y un auto detenido en la cola sigue visible."""
    tracker = _tracker()
    obj_filter = FixedObjectFilter(active=True, fixed_time_s=10)
    diagonal = (1280 ** 2 + 720 ** 2) ** 0.5
    t = 0.0
    for step in range(200):   # 20 s a 10 análisis por segundo
        t = step * 0.1
        x = min(600, 100 + step * 20)   # el auto llega y se detiene en la cola
        dets = [_det(1, "truck", [900, 50, 1100, 200], 0.6), _det(2, "car", [x, 500, x + 150, 600], 0.9)]
        vehicles = tracker.update_tracks(dets, [], 1280, 720, now=t)
        obj_filter.update_state(vehicles, 0.1, t, diagonal)
    visible = {v.track_id for v in tracker.visible(t)}
    assert visible == {2}
    assert obj_filter.fixed_count == 1


def test_class_voting_predicted_box():
    """Comprueba la votación de clase y que la caja predicha avanza con la velocidad."""
    tracker = _tracker()
    for step, cls_name in enumerate(["car", "car", "truck", "car", "car"]):
        x = 100 + step * 10
        tracker.update_tracks([_det(1, cls_name, [x, 400, x + 100, 480], 0.8)], [], 1280, 720, now=step * 0.1)
    vehicle = tracker.vehicles[1]
    assert vehicle.class_name == "car"
    assert vehicle._slope[0] > 50                        # ~100 px/s hacia la derecha
    predicted = vehicle.predicted_box(0.4 + 0.2)
    assert predicted[0] > vehicle.bbox[0]


def test_new_id_reattaches_no_double_count():
    """Comprueba que un cambio de ID tras cruzar la línea no cuenta el vehículo dos veces."""
    from app.vision.counting_lines import CountLine
    tracker = _tracker()
    line = CountLine("line_1", "L1", [0.5, 0.0], [0.5, 1.0])
    for step in range(30):
        x = 400 + step * 15
        tid = 1 if step < 16 else 9         # el tracker cambia la ID justo después de cruzar
        if step in (16, 17):
            continue                        # la IA lo pierde dos análisis
        tracker.update_tracks([_det(tid, "car", [x, 400, x + 120, 480], 0.9)], [line], 1280, 720, now=step * 0.1)
    assert tracker.total_counted == 1
    assert list(tracker.vehicles) == [9]
