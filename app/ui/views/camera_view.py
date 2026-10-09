from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QMenu,
    QPushButton, QVBoxLayout, QWidget,
)

from ...core.app_config import AppConfig
from ...vision.counting_lines import MAX_LINES
from ..components import Card, FlowLayout, PageHeader, ResponsiveGrid, StatCard, StatusChip, icons
from ..styles.theme import set_prop
from ..widgets.video_surface import VideoSurface
from ..scale import px


def _button(text, icon, variant="secondary", icon_color="text", tip=""):
    """Crea un botón con icono, estilo y ayuda."""
    button = QPushButton(text)
    button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tip)
    icons.apply(button, icon, icon_color, 16)
    return button


class _PlaneDialog(QDialog):
    """Pide las medidas reales del rectangulo marcado sobre la calzada."""

    def __init__(self, parent=None):
        """Arma el dialogo con una nota de referencias y los campos de ancho y largo."""
        super().__init__(parent)
        self.setWindowTitle("Medidas del rectángulo")
        layout = QVBoxLayout(self)
        tip = QLabel("Escribe las medidas reales sobre la calle.\n"
                       "Referencias comunes: ancho de carril 3.0–3.6 m · raya discontinua 3–4.5 m "
                       "con separación de 5–9 m · franjas de paso peatonal 0.5 m.")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # Campos en metros con valores iniciales tipicos de un carril
        form = QFormLayout()
        self.width_spin = QDoubleSpinBox()
        self.length_spin = QDoubleSpinBox()
        for spin, value in ((self.width_spin, 3.5), (self.length_spin, 6.0)):
            spin.setRange(0.2, 200.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.1)
            spin.setSuffix(" m")
            spin.setValue(value)
        form.addRow("Ancho (esquina 1 → 2)", self.width_spin)
        form.addRow("Largo (esquina 2 → 3)", self.length_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def ask(self):
        """Muestra el dialogo y devuelve (ancho, largo) o None si se cancela."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.width_spin.value(), self.length_spin.value()
        return None


class CameraView(QWidget):
    """Página de cámara: video en vivo, líneas de conteo, zona de detección y calibración.

    También controla la grabación y muestra indicadores que se actualizan cada segundo.
    Los estilos están en app/ui/styles/views/camera_view.css.
    """

    record_toggled = pyqtSignal()
    add_line = pyqtSignal()
    remove_line = pyqtSignal()
    reset_count = pyqtSignal()
    reference_calibrated = pyqtSignal(list, list, float)    # tramo: a, b, metros
    plane_calibrated = pyqtSignal(list, float, float)       # plano: 4 esquinas, ancho, largo
    configure_camera = pyqtSignal()
    zone_editing = pyqtSignal(bool)                         # empieza / termina la edición
    zone_saved = pyqtSignal(object)                         # DetectionZone

    def __init__(self, parent=None):
        """Arma el encabezado con acciones, el video con su barra y la fila de indicadores."""
        super().__init__(parent)
        # Umbrales de ocupación de [congestion_colors] en analytics.conf
        thresholds = AppConfig.get_instance().section("analytics", "congestion_colors")
        self.medium_threshold = thresholds.get("level_medium", 40)
        self.high_threshold = thresholds.get("level_high", 70)

        root = QVBoxLayout(self)
        root.setContentsMargins(px(24), px(20), px(24), px(24))
        root.setSpacing(px(16))

        # Encabezado con los botones de zona, calibración y grabación
        header = PageHeader("Monitoreo en vivo", "Detección, seguimiento y conteo de vehículos")
        self.btn_calibrate = _button("  Calibrar", "action_ruler",
                                   tip="Marca sobre la calle medidas reales para calcular bien la velocidad")
        menu = QMenu(self.btn_calibrate)
        menu.addAction("Plano de 4 puntos (recomendado)", lambda: self._start_calibration(4))
        menu.addAction("Tramo de 2 puntos", lambda: self._start_calibration(2))
        self.btn_calibrate.setMenu(menu)
        self.btn_zone = _button("  Zona", "action_zone",
                               tip="Dibuja el área donde se buscan vehículos: lo de afuera (letreros, "
                                     "aceras, estacionamientos) se ignora")
        self.btn_zone.clicked.connect(self._toggle_zone)
        header.add_action(self.btn_zone)
        header.add_action(self.btn_calibrate)
        self.btn_record = _button("  Grabar", "record_start")
        self.btn_record.setObjectName("btnRecord")
        self.btn_record.clicked.connect(self.record_toggled.emit)
        header.add_action(self.btn_record)
        root.addWidget(header)

        # Video con barra de herramientas: estado de fuente, calibración e IA y botones de líneas
        card = Card(margin=12, spacing=8)
        bar = QHBoxLayout()
        bar.setSpacing(px(8))
        # Los indicadores pasan a otra línea si la ventana es angosta
        chips = QWidget()
        flow = FlowLayout(chips, spacing=8)
        self.chip_source = StatusChip("Fuente", "Iniciando…", "neutral")
        self.chip_calibration = StatusChip("Calibración", "—", "neutral")
        self.chip_ai = StatusChip("IA", "Cargando…", "neutral")
        for chip in (self.chip_source, self.chip_calibration, self.chip_ai):
            flow.addWidget(chip)
        bar.addWidget(chips, stretch=1)
        self.btn_add = _button("", "action_line_add", "icon", "soft_text", "Agregar línea de conteo")
        self.btn_remove = _button("", "action_line_remove", "icon", "soft_text", "Quitar la última línea")
        self.btn_reset = _button("", "action_reset", "icon", "soft_text", "Reiniciar el conteo en pantalla")
        self.btn_add.clicked.connect(self.add_line.emit)
        self.btn_remove.clicked.connect(self.remove_line.emit)
        self.btn_reset.clicked.connect(self.reset_count.emit)
        for button in (self.btn_add, self.btn_remove, self.btn_reset):
            bar.addWidget(button)
        card.body.addLayout(bar)

        self.video_surface = VideoSurface()
        self.video_surface.reference_marked.connect(self._on_reference)
        self.video_surface.configure_camera.connect(self.configure_camera.emit)
        self.video_surface.zone_finished.connect(self._on_zone_finished)
        self.zone = None
        card.body.addWidget(self.video_surface, stretch=1)
        root.addWidget(card, stretch=1)

        # Indicadores: una fila en pantallas anchas y más filas si no caben
        self.kpi_total = StatCard("Vehículos contados", "status_counter", "accent", "veh", compact=True)
        self.kpi_flow = StatCard("Caudal actual", "status_activity", "success", "veh/min", compact=True)
        self.kpi_speed = StatCard("Velocidad media", "status_gauge", "warning", "km/h", compact=True)
        self.kpi_queue = StatCard("Detenidos", "status_clock", "text", "veh", compact=True)
        self.kpi_congestion = StatCard("Ocupación de vía", "status_road", "success", "%", with_bar=True, compact=True)
        root.addWidget(ResponsiveGrid(
            (self.kpi_total, self.kpi_flow, self.kpi_speed, self.kpi_queue, self.kpi_congestion), spacing=10))

    # --- Zona de detección y calibración ---

    def set_zone(self, zone):
        """Guarda la zona actual y agrega su estado a la ayuda del botón Zona."""
        self.zone = zone
        self.btn_zone.setToolTip(self.btn_zone.toolTip().split("\n")[0] +
                                 ("\nZona activa" if zone.active else "\nSin zona: se analiza todo el video"))

    def _toggle_zone(self):
        """Inicia la edición de la zona o, si ya se esta editando, la guarda."""
        if self.video_surface.editing_zone:
            self.video_surface.finish_zone_edit(save=True)
            return
        if self.zone is None:
            return
        # Entra en modo edición: el botón cambia a "Guardar zona"
        self.video_surface.start_zone_edit(self.zone)
        self.btn_zone.setText("  Guardar zona")
        icons.apply(self.btn_zone, "action_check", "on_accent", 16)
        set_prop(self.btn_zone, "variant", "primary", recursive=False)
        self.zone_editing.emit(True)

    def _on_zone_finished(self, zone, save):
        """Restaura el botón Zona al terminar la edición y emite la zona si se guardo."""
        self.btn_zone.setText("  Zona")
        icons.apply(self.btn_zone, "action_zone", "text", 16)
        set_prop(self.btn_zone, "variant", "secondary", recursive=False)
        self.zone_editing.emit(False)
        if save:
            self.set_zone(zone)
            self.zone_saved.emit(zone)

    def _start_calibration(self, points=4):
        """Inicia el marcado de puntos de calibración sobre el video (2 o 4 puntos)."""
        self.video_surface.start_calibration(points)
        self.video_surface.setFocus()

    def _on_reference(self, points):
        """Pide las medidas reales de los puntos marcados y emite la calibración correspondiente."""
        # Cuatro puntos: calibración por plano con ancho y largo
        if len(points) == 4:
            measures = _PlaneDialog(self).ask()
            if measures:
                self.plane_calibrated.emit(points, *measures)
            return
        # Dos puntos: calibración por tramo con su longitud en metros
        meters, ok = QInputDialog.getDouble(
            self, "Calibración", "¿Cuántos metros mide el tramo que marcaste?\n"
            "(Ejemplo: raya discontinua del carril ≈ 3 m, ancho de carril ≈ 3.5 m)",
            3.5, 0.2, 500.0, 2)
        if ok:
            self.reference_calibrated.emit(points[0], points[1], meters)

    # --- API usada por la ventana principal ---

    def set_lines(self, lines):
        """Muestra las líneas de conteo y habilita agregar o quitar según su cantidad."""
        self.video_surface.set_lines(lines)
        self.btn_add.setEnabled(len(lines) < MAX_LINES)
        self.btn_remove.setEnabled(len(lines) > 1)

    def set_signal(self, has_signal):
        """Refleja si hay señal de video y habilita o deshabilita las acciones que la necesitan."""
        self.video_surface.set_no_signal(not has_signal)
        if not has_signal:
            self.chip_source.set_state("error", "Sin cámara")
        for button in (self.btn_record, self.btn_calibrate, self.btn_zone):
            button.setEnabled(has_signal)

    def update_metrics(self, stats):
        """Actualiza los indicadores y los estados de fuente, IA y calibración con las estadísticas."""
        total = f"{stats.get('total_counted', 0):,}".replace(",", ".")   # separador de miles igual que Estadísticas
        self.kpi_total.set_value(total, f"{stats.get('vehicles_in_scene', 0)} en escena")
        self.kpi_flow.set_value(stats.get("flow_min", 0), f"≈ {stats.get('flow_hour', 0)} veh/h")
        self.kpi_speed.set_value(f"{stats.get('avg_speed', 0.0):.1f}", "Promedio de la escena")
        self.kpi_queue.set_value(stats.get("stopped", 0), "Vehículos casi quietos (cola)")

        # Nivel de ocupación según los umbrales configurados; el tono solo se cambia si varia
        density = float(stats.get("density_pct", 0.0))
        tone = "success" if density < self.medium_threshold else ("warning" if density < self.high_threshold else "error")
        level = {"success": "Fluido", "warning": "Moderado", "error": "Congestionado"}[tone]
        if tone != self.kpi_congestion._tone:
            self.kpi_congestion.set_tone(tone)
        self.kpi_congestion.set_value(f"{density:.0f}", level, density / 100.0)

        # Estados de fuente, IA (verde desde 10 FPS) y calibración
        self.chip_source.set_state("success", f"{stats.get('source', '')} · {stats.get('fps', 0):.0f} FPS")
        fps_ai = stats.get("fps_ai", 0)
        ai_tone = "neutral" if fps_ai <= 0 else ("success" if fps_ai >= 10 else "warning")
        self.chip_ai.set_state(ai_tone, f"{stats.get('model', '')} · {fps_ai:.0f} FPS")
        ready = stats.get("calibration_ready", False)
        self.chip_calibration.set_state("success" if ready else "warning", stats.get("calibration", "—"))

    def set_recording_state(self, recording, path):
        """Cambia texto, estilo e icono del botón de grabación según el estado."""
        del path
        self.btn_record.setText("  Detener grabación" if recording else "  Grabar")
        self.btn_record.setProperty("variant", "danger" if recording else "secondary")
        set_prop(self.btn_record, "recording", bool(recording), recursive=False)
        icons.apply(self.btn_record, "record_stop" if recording else "record_start",
                      "on_accent" if recording else "text", 16)
