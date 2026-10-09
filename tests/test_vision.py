import random

from app.vision.calibration import SpatialCalibrator
from app.vision.counting_lines import CountLine
from app.vision.geometry import crosses_segment
from app.vision.tracker import VehicleTracker


def test_segment_crossing_direction():
    """Comprueba el sentido del cruce y los casos que no cruzan el segmento."""
    a, b = (0, 5), (10, 5)
    assert crosses_segment((5, 0), (5, 10), a, b) == 1
    assert crosses_segment((5, 10), (5, 0), a, b) == -1
    assert crosses_segment((15, 0), (15, 10), a, b) == 0   # pasa fuera del segmento
    assert crosses_segment((5, 0), (5, 4), a, b) == 0      # no llega a la línea


def _auto_calibrator():
    """Crea un SpatialCalibrator en modo automático sin datos aprendidos."""
    cal = SpatialCalibrator()
    cal.mode = "auto"
    cal.reset_auto()
    cal.set_frame_size(1280, 720)
    return cal


def test_auto_calibration_learns_perspective():
    """Comprueba que la calibración automática aprende la escala según la altura en la imagen."""
    random.seed(1)
    cal = _auto_calibrator()
    for _ in range(200):  # 20 px/m arriba (y=0.2) a 80 px/m abajo (y=0.9)
        y = random.uniform(0.25, 0.9)
        ppm = 20 + (y - 0.2) / 0.7 * 60
        width = 1.8 * ppm
        cal.observe("car", [400, y * 720 - 50, 400 + width, y * 720], 0.9)
    assert cal.auto_ready
    assert abs(cal.meters_between((0, 648), (80, 648)) - 1.0) < 0.1   # cerca de la cámara
    assert abs(cal.meters_between((0, 180), (24, 180)) - 1.0) < 0.2   # lejos


def test_vehicle_counted_once_per_line():
    """Comprueba que un vehículo se cuenta una vez y solo en la línea que cruza."""
    tracker = VehicleTracker(_auto_calibrator())
    tracker.min_hits = 2
    line = CountLine("line_1", "L1", [0.4, 0.0], [0.4, 1.0])
    outside = CountLine("line_2", "L2", [0.8, 0.0], [0.8, 0.3])
    for step in range(40):
        x = 200 + step * 20
        tracker.update_tracks([{"id": 7, "class": "car", "bbox": [x, 500, x + 100, 560], "conf": 0.9}],
                              [line, outside], 1280, 720)
    assert line.total == 1
    assert outside.total == 0
    assert tracker.total_counted == 1
    assert tracker.counts_by_class["car"] == 1


def _plane_calibrator():
    """Crea un SpatialCalibrator en modo plano con un carril de 3.5 x 6 m."""
    import cv2
    import numpy as np
    cal = SpatialCalibrator()
    cal.set_frame_size(1280, 720)
    cal.mode = "plane"
    cal.plane_width, cal.plane_length = 3.5, 6.0
    cal.plane_points = [[0.40, 0.90], [0.62, 0.90], [0.57, 0.55], [0.45, 0.55]]   # carril en perspectiva
    target = np.float32([[0, 0], [3.5, 0], [3.5, 6.0], [0, 6.0]])
    cal._homography = cv2.getPerspectiveTransform(np.float32(cal.plane_points), target)
    return cal


def test_plane_calibration_speed():
    """Comprueba la velocidad medida con la calibración por plano y el efecto de la perspectiva."""
    import numpy as np
    cal = _plane_calibrator()
    inverse = np.linalg.inv(cal._homography)
    points = []
    for i in range(10):                      # 1 s alejandose de la cámara a 5 m/s por el centro del carril
        t = i * 0.1
        x, y, w = inverse @ np.array([1.75, 1.0 + 5 * t, 1.0])
        points.append((t, x / w * 1280, y / w * 720))
    assert abs(cal.trajectory_speed(points) - 18.0) < 0.5            # 5 m/s = 18 km/h
    # El mismo avance en pixeles cerca y lejos de la cámara no es la misma distancia real
    near = cal.meters_between((640, 640), (640, 600))
    far = cal.meters_between((640, 420), (640, 380))
    assert far > near * 1.3


def test_box_moves_smoothly():
    """Comprueba que la caja predicha avanza de forma suave entre análisis con ruido."""
    import random
    random.seed(3)
    tracker = VehicleTracker(_auto_calibrator())
    tracker.min_hits = 1
    positions = []
    for frame in range(90):                  # pantalla a 30 FPS, IA a 10 FPS con ruido de ±6 px
        t = frame / 30
        if frame % 3 == 0:
            x = 100 + 300 * t + random.uniform(-6, 6)
            tracker.update_tracks([{"id": 1, "class": "car", "bbox": [x, 400, x + 120, 480], "conf": 0.9}],
                                  [], 1280, 720, now=t)
        positions.append(tracker.vehicles[1].predicted_box(t)[0])
    steps = [b - a for a, b in zip(positions[30:], positions[31:])]       # tras el arranque
    assert all(0 < p < 20 for p in steps)                                 # avanza siempre, ~10 px por cuadro
    assert max(steps) - min(steps) < 8
