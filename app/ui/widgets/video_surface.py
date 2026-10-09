import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..components import icons
from ..styles.theme import color
from ..scale import px, tx

# Distancia en pixeles para agarrar un extremo o esquina, y límites de esquinas de la zona
GRAB_RADIUS = 22
MIN_CORNERS, MAX_CORNERS = 3, 10


def _distance_to_segment(p, a, b):
    """Devuelve la distancia del punto p al segmento a-b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length_sq = dx * dx + dy * dy or 1e-9
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length_sq))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


class VideoSurface(QWidget):
    """Superficie de video interactiva.

    - Muestra el video y permite arrastrar los extremos de cada línea de conteo.
    - Modo calibración: 4 clics marcan un rectangulo sobre la calzada (plano) o
      2 clics un segmento de largo conocido (tramo).
    - Modo zona: se arrastran las esquinas de la zona de detección; doble clic
      sobre un borde agrega una esquina y clic derecho sobre una esquina la quita.
    - Sin señal: panel con aviso y botón para configurar la cámara.

    Colores en theme.conf, sección [Video_surface].
    """

    lines_changed = pyqtSignal(list)            # durante el arrastre: [CountLine]
    edit_finished = pyqtSignal()                # al soltar (guardar)
    reference_marked = pyqtSignal(list)         # calibración: puntos normalizados (2 o 4)
    configure_camera = pyqtSignal()
    zone_finished = pyqtSignal(object, bool)    # DetectionZone, guardar (False = cancelada)

    def __init__(self, parent=None):
        """Crea la superficie sin imagen, sin líneas y fuera de los modos de edición."""
        super().__init__(parent)
        self.setObjectName("videoSurface")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(px(320), px(240))
        self.setMouseTracking(True)

        self.image = None
        self.lines = []
        self.video_rect = QRectF()
        self._drag = None              # (índice de línea, 'a' | 'b')
        self._calibrating = False
        self._ref_points = []
        self._needed_points = 2
        self.zone = None               # DetectionZone en edición (None = no se edita)
        self._drag_zone = None         # índice de la esquina arrastrada
        self._create_no_signal_panel()

    # --- Panel sin señal ---

    def _create_no_signal_panel(self):
        """Crea el panel que se muestra cuando no hay cámara, con el botón para configurarla."""
        self.panel = QWidget(self)
        self.panel.setObjectName("noSignalPanel")
        layout = QVBoxLayout(self.panel)
        layout.setSpacing(px(10))
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_signal_icon = QLabel()
        self.no_signal_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icons.record(self, lambda: self.no_signal_icon.setPixmap(icons.icon_pixmap("camera_off", "muted_text", 48)))
        self.no_signal_icon.setPixmap(icons.icon_pixmap("camera_off", "muted_text", 48))
        title = QLabel("No hay cámara conectada")
        title.setObjectName("noSignalTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_signal = QLabel("Conecta una cámara USB, inicia la cámara virtual de OBS\n"
                                    "o configura una cámara IP. Se reintenta automáticamente.")
        self.lbl_no_signal.setObjectName("noSignalText")
        self.lbl_no_signal.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = QPushButton("  Configurar cámara")
        button.setProperty("variant", "primary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.configure_camera.emit)
        icons.apply(button, "nav_camera", "on_accent", 16)
        for widget in (self.no_signal_icon, title, self.lbl_no_signal):
            layout.addWidget(widget)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        self.panel.hide()

    def set_no_signal(self, no_signal):
        """Muestra u oculta el panel sin señal; al mostrarlo descarta la última imagen."""
        self.panel.setVisible(no_signal)
        if no_signal:
            self.image = None
        self.update()

    def resizeEvent(self, event):
        """Ajusta el panel sin señal al tamaño del widget."""
        self.panel.setGeometry(self.rect())
        super().resizeEvent(event)

    # --- Imagen, líneas y calibración ---

    def set_lines(self, lines):
        """Asigna las líneas de conteo cuyos extremos se pueden arrastrar."""
        self.lines = lines
        self.update()

    def update_frame(self, image, width, height):
        """Muestra una nueva imagen del video y oculta el panel sin señal si estaba visible."""
        del width, height
        self.image = image
        if self.panel.isVisible():
            self.panel.hide()
        self.update()

    def start_calibration(self, points=2):
        """Inicia el modo calibración: 2 puntos (tramo) o 4 puntos (plano)."""
        if self.editing_zone:
            self.finish_zone_edit(save=False)
        self._calibrating = True
        self._needed_points = points
        self._ref_points = []
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def cancel_calibration(self):
        """Sale del modo calibración y descarta los puntos marcados."""
        self._calibrating = False
        self._ref_points = []
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    # --- Zona de detección ---

    @property
    def editing_zone(self):
        """Indica si se esta editando la zona de detección."""
        return self.zone is not None

    def start_zone_edit(self, zone):
        """Inicia la edición sobre una copia de la zona, activandola."""
        self.cancel_calibration()
        self.zone = zone.copy_zone()
        self.zone.active = True
        self.setFocus()
        self.update()

    def finish_zone_edit(self, save=True):
        """Termina la edición y emite zone_finished con la zona y si se debe guardar."""
        if self.zone is None:
            return
        zone, self.zone = self.zone, None
        self._drag_zone = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        self.zone_finished.emit(zone, save)

    def _nearest_corner(self, pos):
        """Devuelve el índice de la esquina de la zona más cercana a pos, o None si esta lejos."""
        best, distance = None, GRAB_RADIUS
        for i, point in enumerate(self.zone.points):
            p = self._to_widget(point)
            d = math.hypot(pos.x() - p.x(), pos.y() - p.y())
            if d <= distance:
                best, distance = i, d
        return best

    def _nearest_edge(self, pos):
        """Devuelve el índice del borde de la zona más cercano a pos, o None si esta lejos."""
        points = [self._to_widget(p) for p in self.zone.points]
        best, distance = None, GRAB_RADIUS
        for i, a in enumerate(points):
            d = _distance_to_segment(pos, a, points[(i + 1) % len(points)])
            if d <= distance:
                best, distance = i, d
        return best

    def _paint_zone(self, p):
        """Oscurece lo que queda fuera de la zona y dibuja su borde, sus esquinas y la ayuda."""
        # Sombra fuera del poligono
        polygon = QPolygonF([self._to_widget(pt) for pt in self.zone.points])
        outside = QPainterPath()
        outside.addRect(self.video_rect)
        inside = QPainterPath()
        inside.addPolygon(polygon)
        inside.closeSubpath()
        shadow = color("video_background", "#07090d")
        shadow.setAlpha(150)
        p.fillPath(outside.subtracted(inside), shadow)

        # Borde discontinuo y esquinas cuadradas
        border = color("accent")
        p.setPen(QPen(border, 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(polygon)
        p.setPen(QPen(border, 2))
        p.setBrush(color("window"))
        for point in polygon:
            p.drawRect(QRectF(point.x() - px(7), point.y() - px(7), px(14), px(14)))
        self._paint_help(p, "Arrastra las esquinas · Doble clic en un borde: agregar · Clic derecho: quitar · "
                              "Enter: guardar · Supr: sin zona · Esc: cancelar")

    def _paint_help(self, p, text):
        """Dibuja una barra de ayuda en la parte superior del video, recortando el texto si no cabe."""
        bar = QRectF(self.video_rect.x(), self.video_rect.y(), self.video_rect.width(), tx(34))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(bar, color("window"))
        p.setPen(color("text"))
        area = bar.adjusted(px(12), 0, -px(12), 0)
        text = p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(area.width()))
        p.drawText(area, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, text)

    # --- Conversión de coordenadas ---

    def _rect_video(self):
        """Calcula el rectangulo donde cabe la imagen centrada conservando su proporción."""
        if self.image is None or self.image.isNull():
            return QRectF(self.rect())
        ratio = self.image.width() / max(1, self.image.height())
        width, height = self.width(), self.height()
        if width / max(1, height) > ratio:
            h, w = height, height * ratio
        else:
            w, h = width, width / ratio
        return QRectF((width - w) / 2, (height - h) / 2, w, h)

    def _to_widget(self, point):
        """Convierte un punto normalizado (0 a 1) en coordenadas del widget."""
        r = self.video_rect
        return QPointF(r.x() + point[0] * r.width(), r.y() + point[1] * r.height())

    def _to_normal(self, pos):
        """Convierte una posición del widget en un punto normalizado (0 a 1) dentro del video."""
        r = self.video_rect
        if r.width() <= 0 or r.height() <= 0:
            return [0.5, 0.5]
        return [max(0.0, min(1.0, (pos.x() - r.x()) / r.width())),
                max(0.0, min(1.0, (pos.y() - r.y()) / r.height()))]

    def _nearest_handle(self, pos):
        """Devuelve (índice de línea, extremo) del extremo más cercano a pos, o None si esta lejos."""
        best, distance = None, GRAB_RADIUS
        for i, line in enumerate(self.lines):
            for end in ("a", "b"):
                p = self._to_widget(getattr(line, end))
                d = math.hypot(pos.x() - p.x(), pos.y() - p.y())
                if d <= distance:
                    best, distance = (i, end), d
        return best

    # --- Dibujo ---

    def paintEvent(self, event):
        """Dibuja el fondo, la imagen y, según el modo, la zona, las asas o la calibración."""
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 10, 10)
        p.setClipPath(clip)
        p.fillRect(self.rect(), color("video_background", "#07090d"))

        self.video_rect = self._rect_video()
        if self.image is None or self.image.isNull():
            return
        p.drawImage(self.video_rect, self.image)

        if self.editing_zone:
            self._paint_zone(p)
            return

        # Asas de las líneas (los trazos y etiquetas ya vienen dibujados en el video)
        handle_a, handle_b = color("video_handle_a", "#22d67a"), color("video_handle_b", "#ff5a5f")
        p.setBrush(Qt.BrushStyle.NoBrush)
        for line in self.lines:
            for end, c in (("a", handle_a), ("b", handle_b)):
                c.setAlpha(210)
                p.setPen(QPen(c, 2, Qt.PenStyle.DashLine))
                p.drawEllipse(self._to_widget(getattr(line, end)), px(14), px(14))

        if self._calibrating:
            self._paint_calibration(p)

    # Instrucciones de calibración para tramo (2 puntos) y plano (4 puntos)
    _SEGMENT_STEPS = ("Clic en un extremo de un tramo de largo conocido", "Clic en el otro extremo")
    _PLANE_STEPS = ("Esquina 1: borde izquierdo del carril, lo más cerca de la cámara",
                    "Esquina 2: borde derecho a la misma altura (1 → 2 = ancho)",
                    "Esquina 3: borde derecho, más lejos (2 → 3 = largo)",
                    "Esquina 4: borde izquierdo a la altura de la esquina 3")

    def _paint_calibration(self, p):
        """Muestra la instrucción del paso actual y los puntos ya marcados unidos por líneas."""
        steps = self._PLANE_STEPS if self._needed_points == 4 else self._SEGMENT_STEPS
        step = steps[min(len(steps) - 1, len(self._ref_points))]
        self._paint_help(p, f"Calibración · {step}  (Esc cancela)")
        points = [self._to_widget(pt) for pt in self._ref_points]
        notice = color("warning")
        p.setPen(QPen(notice, 2))
        for a, b in zip(points, points[1:]):
            p.drawLine(a, b)
        p.setBrush(notice)
        for i, point in enumerate(points, start=1):
            p.drawEllipse(point, 5, 5)
            p.drawText(point + QPointF(8, -8), str(i))
        p.setBrush(Qt.BrushStyle.NoBrush)

    # --- Teclado y ratón ---

    def keyPressEvent(self, event):
        """En la zona: Esc cancela, Enter guarda y Supr la desactiva. En calibración, Esc cancela."""
        if self.editing_zone:
            if event.key() == Qt.Key.Key_Escape:
                self.finish_zone_edit(save=False)
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.finish_zone_edit(save=True)
            elif event.key() == Qt.Key.Key_Delete:   # desactiva la zona: se analiza todo el video
                self.zone.active = False
                self.finish_zone_edit(save=True)
            return
        if event.key() == Qt.Key.Key_Escape and self._calibrating:
            self.cancel_calibration()
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Agrega una esquina a la zona en el borde donde se hizo doble clic."""
        if self.editing_zone and len(self.zone.points) < MAX_CORNERS:
            border = self._nearest_edge(event.position())
            if border is not None:
                self.zone.points.insert(border + 1, self._to_normal(event.position()))
                self.update()

    def mousePressEvent(self, event):
        """Segun el modo: toma o quita una esquina, marca un punto de calibración o toma un extremo."""
        # Edición de zona: clic derecho quita la esquina, izquierdo la toma para arrastrar
        if self.editing_zone:
            self.setFocus()
            corner = self._nearest_corner(event.position())
            if event.button() == Qt.MouseButton.RightButton:
                if corner is not None and len(self.zone.points) > MIN_CORNERS:
                    del self.zone.points[corner]
                    self.update()
            elif event.button() == Qt.MouseButton.LeftButton:
                self._drag_zone = corner
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # Calibración: al completar los puntos se emite reference_marked
        if self._calibrating:
            self._ref_points.append(self._to_normal(event.position()))
            self.update()
            if len(self._ref_points) == self._needed_points:
                points = list(self._ref_points)
                self.cancel_calibration()
                self.reference_marked.emit(points)
            return
        self._drag = self._nearest_handle(event.position())
        self.setFocus()

    def mouseMoveEvent(self, event):
        """Arrastra la esquina o el extremo tomado, o cambia el cursor al pasar cerca de uno."""
        pos = event.position()
        if self.editing_zone:
            if self._drag_zone is not None:
                self.zone.points[self._drag_zone] = self._to_normal(pos)
                self.update()
            else:
                near = self._nearest_corner(pos) is not None
                self.setCursor(Qt.CursorShape.SizeAllCursor if near else Qt.CursorShape.ArrowCursor)
            return
        if self._drag is not None:
            index, end = self._drag
            setattr(self.lines[index], end, self._to_normal(pos))
            self.lines_changed.emit(self.lines)
            self.update()
        elif not self._calibrating:
            near = self._nearest_handle(pos) is not None
            self.setCursor(Qt.CursorShape.SizeAllCursor if near else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        """Suelta la esquina o el extremo; al soltar un extremo emite edit_finished para guardar."""
        if self.editing_zone:
            self._drag_zone = None
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag is not None:
            self._drag = None
            self.edit_finished.emit()
