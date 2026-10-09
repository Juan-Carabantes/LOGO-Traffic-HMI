import copy
import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ..analytics.history import HistoryStore
from ..core.alarms import AlarmManager
from ..core.app_config import AppConfig
from ..core.hardware_detector import update_interval_ms
from ..core.settings import ICON_PATH
from ..plc.controller import PlcController
from ..vision.calibration import points_text
from ..vision.counting_lines import CountLine, new_id
from ..vision.video_worker import VideoWorker
from ..vision.zone import load_zone
from .dialogs.alarms_popup import AlarmsPopup
from .navigation.sidebar import PAGES, CollapsibleSidebar
from .navigation.top_bar import TopBar
from .scale import px, target_screen
from .styles.theme import reload_theme
from .views.analytics_view import AnalyticsView
from .views.camera_view import CameraView
from .views.hmi_view import HmiView
from .views.recommendations_view import RecommendationsView
from .views.settings_view import SettingsView

_log = logging.getLogger(__name__)
PAGE_HMI, PAGE_CAMERA, PAGE_STATS, PAGE_RECOMMEND, PAGE_SETTINGS = range(5)


def _scrollable(view):
    """Pone una vista dentro de un área con desplazamiento que solo aparece si el contenido no cabe."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(view)
    return scroll


class MainWindow(QMainWindow):
    """Ventana principal: compone la interfaz y conecta los módulos entre si.

    No contiene lógica de negocio: el PLC esta en app/plc/controller.py, el video en
    app/vision/video_worker.py, el historial en app/analytics/history.py y las
    alarmas en app/core/alarms.py.
    """

    def __init__(self):
        """Crea los servicios, arma la interfaz, conecta señales e inicia el video."""
        super().__init__()
        self.cfg = AppConfig.get_instance()
        self._has_video = False

        # Título, tamaño mínimo e icono de la ventana
        self.setWindowTitle(self.cfg.get_text("app", "window_title", "LOGO! Traffic HMI"))
        # El mínimo se escala con la pantalla y nunca supera el área útil disponible
        area = target_screen().availableGeometry()
        self.setMinimumSize(min(px(self.cfg.get("ui", "min_width", default=1100)), area.width()),
                            min(px(self.cfg.get("ui", "min_height", default=680)), area.height()))
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        # Servicios: historial, alarmas, PLC y video
        self.history = HistoryStore()
        self.alarms = AlarmManager()
        self.plc = PlcController(self)
        self.video = VideoWorker()

        self._build()
        self._connect()
        self._shortcuts()
        self._start_timers()

        # Estado inicial de la vista de cámara y arranque del video
        self.camera_view.set_lines(self.video.get_lines())
        self.camera_view.set_zone(self.video.get_zone())
        self.video.load_totals(self.history.totals())   # conteo acumulado del historial
        self.video.start()
        if self.cfg.get("ui", "start_maximized", default=True):
            self.showMaximized()

    # --- Construcción ---

    def _build(self):
        """Arma la barra lateral, la barra superior y la pila de páginas."""
        central = QWidget()
        central.setObjectName("appBackground")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = CollapsibleSidebar()
        root.addWidget(self.sidebar)

        # Columna de contenido: barra superior y páginas
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.top_bar = TopBar()
        content.addWidget(self.top_bar)

        # Páginas en el mismo orden que PAGE_HMI, PAGE_CAMERA, PAGE_STATS, PAGE_RECOMMEND y PAGE_SETTINGS
        self.stack = QStackedWidget()
        self.stack.setObjectName("pages")
        self.hmi_view = HmiView()
        self.camera_view = CameraView()
        self.analytics_view = AnalyticsView(self.history)
        self.recommend_view = RecommendationsView()
        self.analytics_view.report_rows = self.recommend_view.report_rows
        self.settings_view = SettingsView()
        # Semáforo y Cámara se envuelven en un área con desplazamiento: si la pantalla es pequeña
        # y el contenido no cabe, aparece la barra en lugar de encimarse (Estadísticas y
        # Configuración ya tienen la suya)
        for view in (self.hmi_view, self.camera_view):
            self.stack.addWidget(_scrollable(view))
        for view in (self.analytics_view, self.recommend_view, self.settings_view):
            self.stack.addWidget(view)
        content.addWidget(self.stack, stretch=1)
        root.addLayout(content, stretch=1)

    def _connect(self):
        """Conecta las señales de las vistas con el PLC, el video, el historial y las alarmas."""
        # Navegación y dialogos
        self.sidebar.page_changed.connect(self._go_to_page)
        self.top_bar.alarms_clicked.connect(self._show_alarms)

        # PLC
        self.top_bar.connect_clicked.connect(self.plc.toggle)
        self.top_bar.ip_changed.connect(self._on_ip_changed)
        self.plc.connection_state.connect(self._on_connection_state)
        self.plc.circuit_state.connect(self._on_circuit_state)
        self.plc.lights.connect(self.hmi_view.traffic_light.set_lights)
        self.plc.io_updated.connect(self.hmi_view.update_io)
        self.plc.message.connect(self.hmi_view.add_log)
        self.hmi_view.control_requested.connect(self.plc.send_order)

        # Video, líneas de conteo, calibración y zona de detección
        surface = self.camera_view.video_surface
        self.video.frame_ready.connect(surface.update_frame)
        self.video.signal_changed.connect(self._on_video_signal)
        self.video.recording_changed.connect(self._on_recording)
        self.video.stats_updated.connect(self._on_stats)
        self.video.crossings_detected.connect(self.history.record_crossings)
        self.video.error_occurred.connect(lambda text: self.log(f"[Cámara] {text}"))
        surface.lines_changed.connect(lambda lines: self.video.set_lines(copy.deepcopy(lines)))
        surface.edit_finished.connect(self.video.save_lines)
        self.camera_view.record_toggled.connect(self.video.toggle_recording)
        self.camera_view.add_line.connect(self._add_line)
        self.camera_view.remove_line.connect(self._remove_line)
        self.camera_view.reset_count.connect(self._reset_count)
        self.camera_view.reference_calibrated.connect(self._on_reference_calibrated)
        self.camera_view.plane_calibrated.connect(self._on_plane_calibrated)
        self.camera_view.configure_camera.connect(lambda: self._open_settings("camera"))
        self.camera_view.zone_editing.connect(self.video.set_zone_editing)
        self.camera_view.zone_saved.connect(self._on_zone_saved)

        # Estadísticas
        self.analytics_view.message.connect(self.log)

        # Configuración
        self.settings_view.settings_saved.connect(self._on_settings_saved)
        self.settings_view.theme_changed.connect(self.reload_styles)
        self.settings_view.calibrate_on_video.connect(self._calibrate_in_video)
        self.settings_view.reset_calibration.connect(self._reset_calibration)
        self.settings_view.edit_zone.connect(self._edit_zone)
        self.settings_view.forget_fixed_objects.connect(self._forget_fixed_objects)

        # Alarmas
        self.alarms.subscribe(self._on_alarm)

    def _shortcuts(self):
        """Registra el atajo para recargar estilos y Ctrl+1..N para cambiar de página."""
        key = self.cfg.get_text("ui", "reload_styles_key", "F5")
        if key:
            QShortcut(QKeySequence(key), self, activated=self.reload_styles)
        for index in range(len(PAGES)):
            QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self,
                      activated=lambda i=index: self._go_to_page(i))

    def _start_timers(self):
        """Inicia los temporizadores de datos en tiempo real y de alarmas por tiempo."""
        # Datos en vivo: guarda los cruces y refresca las estadísticas visibles (update_interval)
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._refresh_live)
        self._live_timer.start(update_interval_ms())

        self._alarm_timer = QTimer(self)   # condiciones que dependen del tiempo (sin video)
        self._alarm_timer.timeout.connect(self._evaluate_time_alarms)
        self._alarm_timer.start(1000)

    # --- Utilidades ---

    def log(self, text):
        """Escribe el mensaje en el log de la aplicación y en el registro de la vista HMI."""
        _log.info(text)
        self.hmi_view.add_log(text)

    def _refresh_live(self):
        """Guarda los datos pendientes y refresca estadísticas si esa página esta visible."""
        self.history.flush()
        if self.stack.currentIndex() == PAGE_STATS and self.isVisible():
            self.analytics_view.refresh_history()

    def _go_to_page(self, index):
        """Muestra la página indicada y actualiza el título y la barra lateral."""
        self.stack.setCurrentIndex(index)
        self.top_bar.set_title(PAGES[index][1])
        self.sidebar.set_active_page(index)
        if index == PAGE_STATS:
            self.analytics_view.refresh_history()

    def _open_settings(self, section):
        """Abre la página de configuración en la sección indicada."""
        self._go_to_page(PAGE_SETTINGS)
        self.settings_view.show_section(section)

    # --- PLC ---

    def _on_ip_changed(self, ip):
        """Guarda la nueva IP del Logo y la refleja en la configuración."""
        if ip:
            self.cfg.set("plc", "ip", ip)
            self.settings_view.txt_plc_ip.setText(ip)

    def _on_connection_state(self, state, text):
        """Actualiza la interfaz y las alarmas según el estado del enlace con el Logo."""
        self.top_bar.set_connection_state(state, text)
        self.hmi_view.set_controls_enabled(state == "connected")
        if state in ("disconnected", "error"):
            self.hmi_view.io_off()
        lost = state in ("reconnecting", "error")
        self.alarms.evaluate("plc_link", lost, "Sin enlace con el LOGO!", "critical")
        if state == "disconnected":
            self.alarms.deactivate("plc_stop")

    def _on_circuit_state(self, kind, text):
        """Muestra el estado del circuito y activa la alarma si el Logo esta en STOP."""
        self.top_bar.set_circuit_state(kind, text)
        self.hmi_view.set_circuit_state(kind, text)
        self.alarms.evaluate("plc_stop", text == "LOGO! en STOP", "El LOGO! está en STOP", "warning")

    # --- Video ---

    def _on_video_signal(self, has_signal):
        """Registra si hay señal de video y resuelve la alarma de falta de video."""
        self._has_video = has_signal
        self.camera_view.set_signal(has_signal)
        if has_signal:
            self.alarms.deactivate("no_video")

    def _on_stats(self, stats):
        """Reparte las estadísticas del video entre vistas e historial y evalua alarmas."""
        self.camera_view.update_metrics(stats)
        self.analytics_view.update_stats(stats)
        self.recommend_view.update_stats(stats)
        self.settings_view.set_calibration_state(stats.get("calibration", "—"))
        self.history.record_sample(stats)

        # Alarmas de congestión y cola con los umbrales de [alarms] en analytics.conf
        a = self.cfg.section("analytics", "alarms")
        self.alarms.evaluate("congestion", stats.get("density_pct", 0) >= a.get("congestion_pct", 75),
                             f"Congestión: ocupación ≥ {a.get('congestion_pct', 75)} %", "warning",
                             a.get("congestion_delay_s", 60))
        self.alarms.evaluate("queue", stats.get("stopped", 0) >= a.get("queue_vehicles", 6),
                             f"Cola larga: {stats.get('stopped', 0)} vehículos detenidos", "warning",
                             a.get("queue_delay_s", 30))

    def _evaluate_time_alarms(self):
        """Activa la alarma de falta de video cuando no hay señal durante el retardo configurado."""
        if not self._has_video:
            delay = self.cfg.get("analytics", "no_video_delay_s", default=10)
            self.alarms.evaluate("no_video", True, "Sin señal de video", "warning", delay)

    def _on_recording(self, recording, path):
        """Refleja el estado de grabación en la vista de cámara y en el registro."""
        self.camera_view.set_recording_state(recording, path)
        self.log(f"Grabando en {path}" if recording else "Grabación detenida.")

    def _add_line(self):
        """Agrega una línea de conteo nueva, desplazada para no encimarse con las demás."""
        lines = self.video.get_lines()
        ident, number = new_id(lines)
        if ident is None:
            return
        offset = 0.1 * (len(lines) % 4)
        lines.append(CountLine(ident, f"Línea {number}",
                                  [0.2, 0.4 + offset], [0.8, 0.4 + offset]))
        self._apply_lines(lines)
        self.log(f"Línea {number} agregada. Arrastra sus extremos sobre el video.")

    def _remove_line(self):
        """Quita la última línea de conteo, dejando siempre al menos una."""
        lines = self.video.get_lines()
        if len(lines) > 1:
            removed = lines.pop()
            self._apply_lines(lines)
            self.log(f"{removed.name} eliminada.")

    def _apply_lines(self, lines):
        """Aplica y guarda las líneas en el video y las muestra en la vista de cámara."""
        self.video.set_lines(lines)
        self.video.save_lines()
        self.camera_view.set_lines(self.video.get_lines())

    def _reset_count(self):
        """Reinicia el conteo en pantalla sin borrar el historial."""
        self.video.reset_count()
        self.log("Conteo en pantalla reiniciado (el historial se conserva).")

    def _edit_zone(self):
        """Va a la página de cámara y activa la edición de la zona de detección."""
        self._go_to_page(PAGE_CAMERA)
        self.camera_view._toggle_zone()

    def _on_zone_saved(self, zone):
        """Aplica la zona de detección guardada y la refleja en la configuración."""
        self.video.set_zone(zone)
        self.settings_view.set_zone_active(zone.active)
        self.log(f"Zona de detección guardada ({len(zone.points)} esquinas)." if zone.active
                 else "Zona de detección desactivada: se analiza todo el video.")

    def _forget_fixed_objects(self):
        """Olvida los objetos fijos aprendidos para que se vuelvan a aprender."""
        self.video.forget_fixed_objects()
        self.log("Objetos fijos olvidados: se volverán a aprender.")

    def _calibrate_in_video(self, points=4):
        """Va a la página de cámara e inicia la calibración marcando puntos sobre el video."""
        self._go_to_page(PAGE_CAMERA)
        self.camera_view._start_calibration(points)

    def _on_plane_calibrated(self, points, width, length):
        """Guarda la calibración por plano (cuatro esquinas y medidas en metros) en vision.conf."""
        self.cfg.set("vision", "calibration", "plane_points", points_text(points))
        self.cfg.set("vision", "calibration", "plane_width_m", round(width, 2))
        self.cfg.set("vision", "calibration", "plane_length_m", round(length, 2))
        self.cfg.set("vision", "calibration", "mode", "plane")
        self.settings_view.set_calibration_mode("plane")
        self.video.update_settings()
        self.log(f"Calibración por plano guardada: rectángulo de {width:g} × {length:g} m.")

    def _on_reference_calibrated(self, a, b, meters):
        """Guarda la calibración manual (dos puntos y su distancia en metros) en vision.conf."""
        self.cfg.set("vision", "calibration", "ref_a", [round(v, 4) for v in a])
        self.cfg.set("vision", "calibration", "ref_b", [round(v, 4) for v in b])
        self.cfg.set("vision", "calibration", "ref_meters", meters)
        self.cfg.set("vision", "calibration", "mode", "manual")
        self.settings_view.set_calibration_mode("manual")
        self.video.update_settings()
        self.log(f"Calibración manual guardada: el tramo marcado mide {meters} m.")

    def _reset_calibration(self):
        """Reinicia la calibración automática para que se aprenda con los proximos vehículos."""
        self.video.reset_calibration()
        self.log("Calibración automática reiniciada: se aprenderá de nuevo con los próximos vehículos.")

    # --- Alarmas ---

    def _on_alarm(self, evt, alarm):
        """Registra la activación o resolución de una alarma y actualiza el indicador."""
        if evt == "activated":
            self.log(f"[Alarma] {alarm.text}")
            self.history.record_alarm(alarm.code, alarm.severity, alarm.text, True)
        elif evt == "deactivated":
            self.log(f"[Alarma resuelta] {alarm.text}")
            self.history.record_alarm(alarm.code, alarm.severity, alarm.text, False)
        self.top_bar.set_alarms(self.alarms.unacked, self.alarms.max_severity)

    def _show_alarms(self):
        """Abre la ventana emergente de alarmas debajo del botón de la barra superior."""
        self._popup = AlarmsPopup(self.alarms, self.history, self)
        self._popup.show_below(self.top_bar.btn_alarms)

    # --- Configuración, estilos y cierre ---

    def _on_settings_saved(self):
        """Aplica la configuración guardada al video, la zona, los temporizadores y el PLC."""
        self.video.update_settings()
        zone = load_zone()
        self.video.set_zone(zone, save=False)
        self.camera_view.set_zone(zone)
        self._live_timer.start(update_interval_ms())
        self.top_bar.set_ip(self.cfg.get_text("plc", "ip", ""))
        self.recommend_view.set_interval(update_interval_ms())
        self.plc.update_reads()
        self.log("Configuración guardada.")

    def reload_styles(self):
        """Recarga el tema (theme.conf y app/ui/styles/) y repinta los elementos dibujados."""
        reload_theme()
        self.hmi_view.traffic_light.update()
        self.camera_view.video_surface.update()
        self.video.update_settings()
        self.log("Tema recargado (app/config/theme.conf y app/ui/styles/).")

    def resizeEvent(self, event):
        """Contrae la barra lateral en ventanas angostas y la vuelve a abrir al ensancharlas."""
        super().resizeEvent(event)
        narrow = event.size().width() < px(1000)
        sidebar = self.sidebar
        if narrow and not sidebar.is_collapsed:
            sidebar.set_collapsed(True, save=False)
            self._auto_collapsed = True
        elif not narrow and getattr(self, "_auto_collapsed", False):
            sidebar.set_collapsed(False, save=False)
            self._auto_collapsed = False

    def closeEvent(self, event):
        """Detiene el PLC y el video y cierra el historial antes de salir."""
        self.plc.shutdown()
        if self.video.isRunning():
            self.video.stop()
        self.history.close()
        logging.getLogger("app").info("=== CIERRE ===")
        event.accept()
