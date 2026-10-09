from PyQt6.QtCore import QSize, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget,
)

from ...core.app_config import CONFIG_DIR, AppConfig
from ...core.hardware_detector import update_interval_ms
from ...core.timers_map import load_timer_blocks
from ...vision.camera_enumerator import list_camera_devices
from ...vision.model_engine import openvino_available
from ..components import Card, PageHeader, icons
from ..scale import FONT_DEFAULTS, font_factor, layout_factor, px, tx

# Secciones de la lista lateral: (clave, texto, icono)
SECTIONS = (
    ("plc", "Conexión S7", "action_plug"),
    ("timers", "Tiempos del LOGO!", "nav_hmi"),
    ("camera", "Cámara", "nav_camera"),
    ("detection", "Detección IA", "status_cpu"),
    ("calibration", "Calibración", "action_ruler"),
    ("stats", "Estadísticas y alarmas", "status_database"),
    ("appearance", "Apariencia", "status_palette"),
)
# Opciones de las listas desplegables: (valor guardado en el .conf, texto visible)
_SOURCES = (("usb", "Cámara USB / OBS"), ("stream", "Cámara IP (RTSP / HTTP)"), ("file", "Archivo de video (pruebas)"))
_PROFILES = (("auto", "Automático (según el hardware)"), ("low", "Bajo · CPU básica"),
             ("medium", "Medio · CPU moderna"), ("high", "Alto · Máxima precisión"))
# Frecuencia de actualización de los datos en vivo (analytics.conf update_interval)
_UPDATES = (("auto", "Automática (según el perfil)"), ("realtime", "Tiempo real (cada 0.5 s)"),
            ("1", "Cada 1 s"), ("2", "Cada 2 s"), ("3", "Cada 3 s"), ("5", "Cada 5 s"), ("10", "Cada 10 s"))
_TRACKERS = (("bytetrack.yaml", "ByteTrack (rápido, recomendado)"), ("botsort.yaml", "BoT-SORT"))
_ENGINES = (("auto", "Automático (OpenVINO si está instalado)"), ("openvino", "OpenVINO (CPU acelerada)"),
            ("pytorch", "PyTorch (GPU NVIDIA o CPU)"))
# Confianza mínima por tipo: (clave en [detection] de vision.conf, texto, valor por defecto)
_CONFIDENCES = (("car_confidence", "Autos", 0.40), ("motorcycle_confidence", "Motocicletas", 0.25),
               ("bus_confidence", "Autobuses", 0.45), ("truck_confidence", "Camiones", 0.45))
_CALIBRATION = (("plane", "Plano de 4 puntos (recomendado)"), ("auto", "Automática (aproximada)"),
                ("manual", "Tramo de 2 puntos"))
_THEMES = (("auto", "Automático (igual que Windows)"), ("dark", "Oscuro"), ("light", "Claro"))
_SCALES = (("auto", "Automática (según la pantalla)"),) + tuple(
    (str(v), f"{v} %") for v in (70, 80, 90, 100, 110, 125, 150))
# Tipos de letra de ui.conf [fonts]: (clave, etiqueta, ayuda)
_FONTS = (
    ("text", "Texto general", "Controles, botones, menús y tablas"),
    ("page_title", "Títulos de página", "Encabezado de cada página (Configuración, Estadísticas…)"),
    ("card_title", "Títulos de tarjeta", "Nombre de cada tarjeta o panel"),
    ("subtitle", "Subtítulos", "Descripciones debajo de los títulos"),
    ("small", "Textos pequeños", "Etiquetas, ayudas, detalles y gráficas"),
    ("value", "Números grandes", "Valores de los indicadores de Estadísticas"),
    ("log", "Registro de eventos", "Terminal de tramas S7, cámara y sistema"),
)


# --- Fabricas de campos (evitan repetir la misma configuración en cada formulario) ---

def _form():
    """Crea un formulario con el espaciado común de la página."""
    form = QFormLayout()
    form.setHorizontalSpacing(px(24))
    form.setVerticalSpacing(px(12))
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return form


def _row(form, text, field, tip=""):
    """Agrega una fila al formulario; la ayuda se aplica a la etiqueta y al campo."""
    label = QLabel(text)
    label.setObjectName("formLabel")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if tip:
        label.setToolTip(tip)
        if isinstance(field, QWidget):
            field.setToolTip(tip)
    form.addRow(label, field)


def _integer(value, min_value, max_value, suffix=""):
    """Crea un campo numérico entero con rango y sufijo."""
    spin = QSpinBox()
    spin.setRange(min_value, max_value)
    spin.setSuffix(suffix)
    spin.setValue(int(value))
    spin.setMaximumWidth(tx(180))
    return spin


def _decimal(value, min_value, max_value, suffix="", step=0.1, decimals=2):
    """Crea un campo numérico decimal con rango, paso y sufijo."""
    spin = QDoubleSpinBox()
    spin.setRange(min_value, max_value)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    spin.setValue(float(value))
    spin.setMaximumWidth(tx(180))
    return spin


def _checkbox(text, value):
    """Crea una casilla con su estado inicial."""
    checkbox = QCheckBox(text)
    checkbox.setChecked(bool(value))
    return checkbox


def _list(options, value):
    """Crea una lista desplegable y selecciona el valor dado, o la primera opción si no existe."""
    combo = QComboBox()
    for key, text in options:
        combo.addItem(text, key)
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)
    return combo


def _button(text, icon, variant="secondary", icon_color="text"):
    """Crea un botón con icono y estilo."""
    button = QPushButton(text)
    button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    icons.apply(button, icon, icon_color, 16)
    return button


def _flash(button, text, icon, color, normal_text, normal_icon, normal_color, ms=3000):
    """Muestra una confirmación temporal en el propio botón y luego devuelve su texto e icono."""
    # El ancho se fija para que el botón no cambie de tamaño con el texto corto
    button.setMinimumWidth(button.width())
    button.setText(text)
    icons.apply(button, icon, color, 16)
    timer = getattr(button, "_flash_timer", None)
    if timer is None:
        timer = QTimer(button)
        timer.setSingleShot(True)
        button._flash_timer = timer
    else:
        timer.timeout.disconnect()
    def restore():
        """Devuelve el texto y el icono normales del botón."""
        button.setText(normal_text)
        icons.apply(button, normal_icon, normal_color, 16)
    timer.timeout.connect(restore)
    timer.start(ms)   # un nuevo clic reinicia los 3 segundos


def _help(text):
    """Crea una etiqueta de ayuda con ajuste de línea."""
    label = QLabel(text)
    label.setObjectName("helpText")
    label.setWordWrap(True)
    return label


def _page(*cards):
    """Apila las tarjetas en una página con desplazamiento vertical."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    container = QWidget()
    container.setObjectName("settingsPage")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(px(4), 0, px(8), px(16))
    layout.setSpacing(px(16))
    for card in cards:
        layout.addWidget(card)
    layout.addStretch(1)
    scroll.setWidget(container)
    return scroll


class _Field:
    """Une un control de la interfaz con su clave en los .conf (leer, escribir, restablecer)."""

    def __init__(self, widget, target, scale=1):
        """Guarda el control, su destino en los .conf y la escala entre valor mostrado y guardado."""
        self.widget = widget
        self.target = target          # (módulo, clave) o (módulo, sección, clave)
        self.scale = scale            # valor guardado = valor mostrado x escala (p. ej. s -> ms)

    @property
    def is_text(self):
        """Indica si el valor se lee de los .conf como texto (campos de texto y listas)."""
        return isinstance(self.widget, (QLineEdit, QComboBox))

    def read_frame(self):
        """Devuelve el valor del control listo para guardar, aplicando la escala."""
        w = self.widget
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QDoubleSpinBox):
            value = w.value() * self.scale
            return int(round(value)) if self.scale != 1 else round(value, w.decimals())
        if isinstance(w, QSpinBox):
            return w.value()
        if isinstance(w, QComboBox):
            return w.currentData()
        return w.text().strip()

    def put(self, value):
        """Muestra en el control un valor leído de los .conf, deshaciendo la escala."""
        w = self.widget
        if isinstance(w, QCheckBox):
            w.setChecked(str(value).lower() in ("true", "1", "yes", "si", "sí"))
        elif isinstance(w, QDoubleSpinBox):
            w.setValue(float(value) / self.scale)
        elif isinstance(w, QSpinBox):
            w.setValue(int(float(value)))
        elif isinstance(w, QComboBox):
            index = w.findData(str(value))
            if index >= 0:
                w.setCurrentIndex(index)
        else:
            w.setText("" if value is None else str(value))


class SettingsView(QWidget):
    """Página de configuración organizada por secciones, con la lista a la izquierda.

    Todo se lee y se guarda en app/config/*.conf al pulsar "Guardar cambios". Cada área
    (tarjeta) tiene un botón "Restablecer" que vuelve solo esa área a los valores de
    fabrica de app/config/defaults/ y la guarda al momento. Los estilos están en
    app/ui/styles/views/settings_view.css.
    """

    settings_saved = pyqtSignal()
    theme_changed = pyqtSignal()
    calibrate_on_video = pyqtSignal(int)          # 4 = plano, 2 = tramo
    reset_calibration = pyqtSignal()
    edit_zone = pyqtSignal()
    forget_fixed_objects = pyqtSignal()

    def __init__(self, parent=None):
        """Arma el encabezado con el botón Guardar, la lista de secciones y sus páginas."""
        super().__init__(parent)
        self.cfg = AppConfig.get_instance()
        self._areas = []              # (card, [_Field], extra)

        root = QVBoxLayout(self)
        root.setContentsMargins(px(24), px(20), px(24), px(24))
        root.setSpacing(px(16))

        # Encabezado con el botón Guardar cambios (la confirmación aparece en el mismo botón)
        header = PageHeader("Configuración", f"Se guarda en {CONFIG_DIR}")
        self.btn_save = _button("  Guardar cambios", "action_save", "primary", "on_accent")
        self.btn_save.clicked.connect(self.save_all)
        header.add_action(self.btn_save)
        root.addWidget(header)

        # Lista de secciones a la izquierda y página de cada sección a la derecha
        body = QHBoxLayout()
        body.setSpacing(px(20))
        self.nav = QListWidget()
        self.nav.setObjectName("navConfig")
        self.nav.setFixedWidth(tx(230))
        self.nav.setIconSize(QSize(tx(18), tx(18)))
        self.nav.setSizeAdjustPolicy(QListWidget.SizeAdjustPolicy.AdjustToContents)   # alto según sus filas
        self.pages = QStackedWidget()
        self._indexes = {}
        builders = {
            "plc": self._section_plc, "timers": self._section_timers, "camera": self._section_camera,
            "detection": self._section_detection, "calibration": self._section_calibration,
            "stats": self._section_stats, "appearance": self._section_appearance,
        }
        # Cada elemento guarda su icono para repintarlo al cambiar el tema
        for key, text, icon in SECTIONS:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, icon)
            self.nav.addItem(item)
            self._indexes[key] = self.pages.addWidget(builders[key]())
        self._paint_icons()
        icons.record(self, self._paint_icons)
        # Alto justo para mostrar todas las secciones sin desplazamiento
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav, alignment=Qt.AlignmentFlag.AlignTop)
        body.addWidget(self.pages, stretch=1)
        root.addLayout(body, stretch=1)
        root.addWidget(self._credits())

    def _credits(self):
        """Crea el pie discreto con el nombre de la aplicación, la versión y el autor."""
        name = self.cfg.get_text("app", "name", "LOGO! Traffic HMI")
        version = self.cfg.get_text("app", "version", "1.0.0")
        label = QLabel(
            f"{name} v{version}  ·  Desarrollado por Juan Carabantes  ·  "
            '<a href="https://github.com/Juan-Carabantes">github.com/Juan-Carabantes</a>')
        label.setObjectName("creditsFooter")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _paint_icons(self):
        """Pinta el icono de cada sección con los colores actuales del tema."""
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            item.setIcon(icons.state_icon(item.data(Qt.ItemDataRole.UserRole), "soft_text", "accent", 18))

    def show_section(self, key):
        """Selecciona la sección indicada por su clave, si existe."""
        if key in self._indexes:
            self.nav.setCurrentRow(self._indexes[key])

    # --- Áreas con "Restablecer" ---

    def _area(self, card, fields, extra=None):
        """Registra los campos de una tarjeta y le agrega su botón Restablecer.

        Cada campo es (control, destino) o (control, destino, escala); extra es una
        función opcional que se ejecuta después de restablecer.
        """
        fields = [_Field(w, target, *options) for w, target, *options in fields]
        self._areas.append((card, fields, extra))
        button = _button("  Restablecer", "action_reset")
        button.setToolTip("Volver a los valores predeterminados solo en esta área")
        button.clicked.connect(lambda: self._reset_area(card, fields, extra, button))
        card.add_action(button)

    def _reset_area(self, card, fields, extra, button=None):
        """Pide confirmación y vuelve los campos del área a los valores de fabrica, guardandolos al momento."""
        title = card.lbl_title.text()
        answer = QMessageBox.question(
            self, "Restablecer valores",
            f"¿Volver «{title}» a los valores predeterminados?\n\nSolo cambia esta área; el resto de la "
            "configuración se queda como está.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        # Restablece y guarda cada campo que tenga valor de fabrica
        cfg = self.cfg
        previous_style = self._style_signature()
        for field in fields:
            value = cfg.default(*field.target, text=field.is_text)
            if value is None:
                continue
            field.put(value)
            cfg.set(*field.target, field.read_frame())
        if extra:
            extra()
        # Avisa del cambio y recarga el tema solo si el modo cambio
        if button is not None:
            _flash(button, "  Restablecido", "action_check", "success",
                   "  Restablecer", "action_reset", "text")
        self.settings_saved.emit()
        if self._style_signature() != previous_style:
            self.theme_changed.emit()
            QTimer.singleShot(0, self._fit_nav)

    def _reset_camera(self):
        """Vuelve a seleccionar la cámara de fabrica y la guarda."""
        index = self.combo_cameras.findData(int(self.cfg.default("camera", "device_index", default=0)))
        self.combo_cameras.setCurrentIndex(max(0, index))
        self._save_camera()

    def _save_camera(self):
        """Guarda el índice y el nombre de la cámara elegida, si se detecto alguna."""
        index = self.combo_cameras.currentData()
        if index is not None and self.combo_cameras.currentText() != "No se detectaron cámaras":
            self.cfg.set("camera", "device_index", int(index))
            self.cfg.set("camera", "device_name", self.combo_cameras.currentText())

    # --- Secciones ---

    def _section_plc(self):
        """Crea la sección de conexión S7 con el Logo (plc.conf)."""
        cfg = self.cfg
        card = Card("Comunicación Ethernet S7", "Parámetros de app/config/plc.conf")
        form = _form()
        self.txt_plc_ip = QLineEdit(cfg.get_text("plc", "ip", "192.168.0.3"))
        self.txt_tsap_local = QLineEdit(cfg.get_text("plc", "tsap_local", "0x0300"))
        self.txt_tsap_remote = QLineEdit(cfg.get_text("plc", "tsap_remote", "0x0200"))
        self.spin_poll = _integer(cfg.get("plc", "poll_interval_ms", default=100), 50, 2000, " ms")
        self.chk_reconnect = _checkbox("Reconectar si se pierde el enlace", cfg.get("plc", "auto_reconnect", default=True))
        self.spin_retry = _integer(cfg.get("plc", "retry_s", default=5), 1, 120, " s")
        _row(form, "Dirección IP del LOGO!", self.txt_plc_ip)
        _row(form, "TSAP local", self.txt_tsap_local)
        _row(form, "TSAP remoto", self.txt_tsap_remote)
        _row(form, "Intervalo de lectura", self.spin_poll)
        _row(form, "", self.chk_reconnect)
        _row(form, "Espera entre reintentos", self.spin_retry)
        card.body.addLayout(form)

        # Campos que vuelven a fabrica con Restablecer
        self._area(card, [(self.txt_plc_ip, ("plc", "ip")), (self.txt_tsap_local, ("plc", "tsap_local")),
                          (self.txt_tsap_remote, ("plc", "tsap_remote")), (self.spin_poll, ("plc", "poll_interval_ms")),
                          (self.chk_reconnect, ("plc", "auto_reconnect")), (self.spin_retry, ("plc", "retry_s"))])
        return _page(card)

    def _section_timers(self):
        """Crea la sección de lectura de tiempos del Logo y la tabla de temporizadores (solo lectura)."""
        cfg = self.cfg
        t = cfg.section("plc", "timers")
        card = Card("Lectura de tiempos del LOGO!", "Solo lectura: el LOGO! no permite cambiar los tiempos desde la app")
        form = _form()
        self.chk_read_times = _checkbox("Leer el tiempo de los temporizadores", t.get("read_times", True))
        self.spin_read_interval = _integer(t.get("read_interval_s", 2), 1, 60, " s")
        self.spin_factor = _integer(t.get("factor", 100), 1, 1000)
        _row(form, "", self.chk_read_times)
        _row(form, "Leer cada", self.spin_read_interval)
        _row(form, "Factor (segundos = valor ÷ factor)", self.spin_factor,
              "Con base de tiempo 's (s:1/100 s)' en el LOGO! usa 100")
        card.body.addLayout(form)
        card.body.addWidget(_help(
            "En LOGO!Soft Comfort abre Herramientas > Asignación de parámetros a VM, asigna el parámetro T de "
            "cada temporizador a una palabra VW y escribe esa dirección abajo. Con 0 no se lee y se muestra el "
            "tiempo programado que escribas aquí (solo como referencia en Estadísticas)."))

        # Tabla de temporizadores: dirección VW de lectura y tiempo programado de cada bloque (timers.conf)
        card_blocks = Card("Temporizadores", "Dirección de lectura y tiempo programado de cada bloque")
        table = QGridLayout()
        table.setHorizontalSpacing(px(16))
        table.setVerticalSpacing(px(10))
        for column, title in enumerate(("Bloque", "Función", "Dirección VW", "Tiempo programado")):
            label = QLabel(title)
            label.setObjectName("formLabel")
            table.addWidget(label, 0, column)
        fields = []
        for row, block in enumerate(load_timer_blocks(), start=1):
            vw = _integer(block.vw_read, 0, 850)   # 0 = no leer
            vw.setSpecialValueText("No leer")
            seconds = _integer(block.seconds, 0, 3600, " s")
            table.addWidget(QLabel(block.id), row, 0)
            table.addWidget(QLabel(block.function), row, 1)
            table.addWidget(vw, row, 2)
            table.addWidget(seconds, row, 3)
            fields += [(vw, ("timers", block.id, "vw_read")),
                       (seconds, ("timers", block.id, "seconds"))]
        table.setColumnStretch(1, 1)
        card_blocks.body.addLayout(table)

        self._area(card, [
            (self.chk_read_times, ("plc", "timers", "read_times")),
            (self.spin_read_interval, ("plc", "timers", "read_interval_s")),
            (self.spin_factor, ("plc", "timers", "factor")),
        ])
        self._area(card_blocks, fields)
        return _page(card, card_blocks)

    def _section_camera(self):
        """Crea la sección de fuente de video, información sobre el video y grabación (camera.conf)."""
        cfg = self.cfg
        card = Card("Fuente de video", "Cámara USB, OBS, cámara IP o archivo de pruebas")
        form = _form()
        self.combo_source = _list(_SOURCES, str(cfg.get("camera", "source_type", default="usb")))
        self.combo_cameras = QComboBox()
        btn_refresh = _button("", "action_refresh", "icon", "soft_text")
        btn_refresh.setToolTip("Buscar cámaras otra vez")
        btn_refresh.clicked.connect(self._load_cameras)
        # Lista de cámaras detectadas con botón para buscar otra vez
        cam_row = QHBoxLayout()
        cam_row.addWidget(self.combo_cameras, stretch=1)
        cam_row.addWidget(btn_refresh)
        self._load_cameras()
        self.txt_stream = QLineEdit(cfg.get_text("camera", "stream_url", ""))
        self.txt_stream.setPlaceholderText("rtsp://usuario:clave@192.168.1.100:554/stream1")
        self.txt_video = QLineEdit(cfg.get_text("camera", "video_file", ""))
        self.spin_width = _integer(cfg.get("camera", "width", default=1280), 320, 3840, " px")
        self.spin_height = _integer(cfg.get("camera", "height", default=720), 240, 2160, " px")
        self.spin_fps = _integer(cfg.get("camera", "fps", default=30), 5, 60, " FPS")
        _row(form, "Tipo de entrada", self.combo_source)
        _row(form, "Cámara", cam_row)
        _row(form, "URL de la cámara IP", self.txt_stream)
        _row(form, "Archivo de video", self._browse_row(self.txt_video, "action_file", self._browse_video))
        _row(form, "Resolución (ancho)", self.spin_width)
        _row(form, "Resolución (alto)", self.spin_height)
        _row(form, "Cuadros por segundo", self.spin_fps)
        self.spin_screen_fps = _integer(cfg.get("camera", "max_screen_fps", default=30), 5, 60, " FPS")
        _row(form, "Máximo en pantalla", self.spin_screen_fps,
              "El video se muestra fluido hasta este valor; la IA analiza tan rápido como pueda tu equipo")
        card.body.addLayout(form)

        # Información dibujada sobre el video ([hud] de camera.conf)
        hud = cfg.section("camera", "hud")
        card_hud = Card("Información sobre el video", "Se dibuja en pantalla y queda en las grabaciones")
        form = _form()
        self.chk_hud = _checkbox("Mostrar panel de información", hud.get("show", True))
        self.chk_hud_date = _checkbox("Fecha y hora", hud.get("show_datetime", True))
        self.chk_hud_source = _checkbox("Fuente de video", hud.get("show_source", True))
        self.chk_hud_fps = _checkbox("FPS y modelo", hud.get("show_fps", True))
        self.chk_hud_count = _checkbox("Conteo, en escena y detenidos", hud.get("show_count", True))
        self.chk_hud_cal = _checkbox("Estado de la calibración", hud.get("show_calibration", True))
        _row(form, "", self.chk_hud)
        for checkbox in (self.chk_hud_date, self.chk_hud_source, self.chk_hud_fps, self.chk_hud_count, self.chk_hud_cal):
            _row(form, "", checkbox)
        card_hud.body.addLayout(form)

        # Carpeta de grabaciones
        card_rec = Card("Grabación", "Videos MP4 con las detecciones dibujadas")
        form = _form()
        self.txt_folder = QLineEdit(cfg.get_text("camera", "recordings_dir", "recordings"))
        _row(form, "Carpeta", self._browse_row(self.txt_folder, "action_folder", self._browse_folder))
        card_rec.body.addLayout(form)

        # La cámara elegida se restablece con _reset_camera como extra del área
        self._area(card, [
            (self.combo_source, ("camera", "source_type")), (self.txt_stream, ("camera", "stream_url")),
            (self.txt_video, ("camera", "video_file")), (self.spin_width, ("camera", "width")),
            (self.spin_height, ("camera", "height")), (self.spin_fps, ("camera", "fps")),
            (self.spin_screen_fps, ("camera", "max_screen_fps")),
        ], self._reset_camera)
        self._area(card_hud, [
            (self.chk_hud, ("camera", "hud", "show")),
            (self.chk_hud_date, ("camera", "hud", "show_datetime")),
            (self.chk_hud_source, ("camera", "hud", "show_source")),
            (self.chk_hud_fps, ("camera", "hud", "show_fps")),
            (self.chk_hud_count, ("camera", "hud", "show_count")),
            (self.chk_hud_cal, ("camera", "hud", "show_calibration")),
        ])
        self._area(card_rec, [(self.txt_folder, ("camera", "recordings_dir"))])
        return _page(card, card_hud, card_rec)

    def _section_detection(self):
        """Crea la sección de detección IA: equipo, modelo, confianzas, zona y seguimiento (vision.conf)."""
        cfg = self.cfg
        hw = cfg.hardware_info

        # Equipo detectado, usado para el perfil automático
        card_hw = Card("Equipo detectado", "Se usa para el perfil automático")
        form = _form()
        gpu = f"{hw['gpu_name']} (CUDA)" if hw["has_cuda"] else "Sin GPU compatible con CUDA"
        _row(form, "Procesador", QLabel(f"{hw['cpu_count']} hilos"))
        _row(form, "Memoria RAM", QLabel(f"{hw['ram_gb']} GB"))
        _row(form, "Tarjeta gráfica", QLabel(gpu))
        names = {"low": "Bajo", "medium": "Medio", "high": "Alto"}
        suggested = QLabel(f"{names.get(hw['suggested_profile'], hw['suggested_profile'])} "
                           "· se aplica solo con el perfil «Automático»")
        suggested.setObjectName("valueHighlight")
        _row(form, "Perfil sugerido", suggested)
        card_hw.body.addLayout(form)

        # Modelo YOLO, motor de inferencia y seguimiento
        card = Card("Modelo de detección", "YOLO26 + seguimiento de vehículos")
        form = _form()
        self.combo_profile = _list(_PROFILES, str(cfg.get_text("vision", "profile", "auto")).lower())
        self.combo_engine = _list(_ENGINES, cfg.get_text("vision", "engine", "auto"))
        ov_state = QLabel("Instalado ✓" if openvino_available() else
                           "No instalado · ejecuta:  pip install openvino")
        ov_state.setObjectName("valueHighlight" if openvino_available() else "helpText")
        ov_state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.spin_iou = _decimal(cfg.get("vision", "iou_nms", default=0.5), 0.1, 0.9, step=0.05)
        self.combo_tracker = _list(_TRACKERS, cfg.get_text("vision", "tracker", "bytetrack.yaml"))
        self.chk_nms_classes = _checkbox("Una sola caja por vehículo (quita duplicados auto/camión y cajas dentro de otras)",
                                       cfg.get("vision", "class_agnostic_nms", default=True))
        _row(form, "Perfil de rendimiento", self.combo_profile)
        _row(form, "Motor de inferencia", self.combo_engine,
              "OpenVINO hace que la IA vaya unas 3 veces más rápido en procesadores Intel y AMD")
        _row(form, "OpenVINO", ov_state)
        _row(form, "Solapamiento (IoU)", self.spin_iou, "Más bajo = elimina más cajas duplicadas")
        _row(form, "Seguidor", self.combo_tracker)
        _row(form, "", self.chk_nms_classes)
        card.body.addLayout(form)

        # Confianza mínima por tipo de vehículo y tamaño mínimo de caja
        d = cfg.section("vision", "detection")
        card_conf = Card("Confianza mínima por tipo", "Cada tipo de vehículo tiene su propio umbral")
        form = _form()
        self.spin_confidences = {}
        for key, text, default in _CONFIDENCES:
            spin = _decimal(d.get(key, default), 0.05, 0.95, step=0.05)
            self.spin_confidences[key] = spin
            _row(form, text, spin)
        self.spin_min_area = _decimal(d.get("min_area_pct", 0.03), 0.0, 2.0, " %", 0.01, 2)
        _row(form, "Tamaño mínimo de caja", self.spin_min_area, "Porcentaje de la imagen; descarta detecciones diminutas")
        card_conf.body.addLayout(form)
        card_conf.body.addWidget(_help(
            "Si no detecta un tipo de vehículo (por ejemplo motos), baja su valor. "
            "Si aparecen detecciones falsas de ese tipo, súbelo."))

        # Zona de detección y objetos fijos
        z = cfg.section("vision", "zone")
        card_zone = Card("Zona de detección y objetos fijos", "Evita que letreros o vallas se detecten como vehículos")
        form = _form()
        self.chk_zone = _checkbox("Analizar solo dentro de la zona dibujada", z.get("active", False))
        btn_zone = _button("  Dibujar zona en el video", "action_zone")
        btn_zone.clicked.connect(self.edit_zone.emit)
        self.chk_fixed = _checkbox("Ocultar objetos que nunca se mueven (letreros, postes…)",
                                  z.get("hide_fixed_objects", True))
        self.spin_fixed_s = _integer(z.get("fixed_object_s", 45), 5, 3600, " s")
        btn_forget = _button("  Olvidar objetos fijos", "action_reset")
        btn_forget.clicked.connect(self.forget_fixed_objects.emit)
        _row(form, "Zona", self.chk_zone)
        _row(form, "", btn_zone)
        _row(form, "Objetos fijos", self.chk_fixed)
        _row(form, "Considerar fijo tras", self.spin_fixed_s,
              "Tiempo quieto en el mismo lugar desde que aparece. Un vehículo en la cola llegó moviéndose, "
              "así que no se oculta.")
        _row(form, "", btn_forget)
        card_zone.body.addLayout(form)

        # Seguimiento, velocidad y elementos dibujados sobre cada vehículo
        t = cfg.section("vision", "tracking")
        card_seg = Card("Seguimiento y velocidad", "Estabilidad del conteo y de la velocidad mostrada")
        form = _form()
        self.spin_min_hits = _integer(t.get("min_hits", 3), 1, 30, " cuadros")
        self.spin_speed_interval = _decimal(t.get("speed_interval_s", 1.0), 0.2, 5.0, " s", 0.1, 1)
        self.spin_stopped = _integer(t.get("stopped_speed_kmh", 5), 1, 30, " km/h")
        self.chk_boxes = _checkbox("Cuadro alrededor de cada vehículo", cfg.get("vision", "show_boxes", default=True))
        self.chk_class = _checkbox("Tipo e identificador", cfg.get("vision", "show_class", default=True))
        self.chk_speed = _checkbox("Velocidad", cfg.get("vision", "show_speed", default=True))
        self.chk_trail = _checkbox("Estela de la trayectoria", cfg.get("vision", "show_trail", default=True))
        _row(form, "Cuadros antes de contar", self.spin_min_hits, "Evita contar detecciones falsas momentáneas")
        _row(form, "Actualizar velocidad cada", self.spin_speed_interval)
        _row(form, "Detenido por debajo de", self.spin_stopped)
        _row(form, "Mostrar", self.chk_boxes)
        for checkbox in (self.chk_class, self.chk_speed, self.chk_trail):
            _row(form, "", checkbox)
        card_seg.body.addLayout(form)

        # Campos que vuelven a fabrica con Restablecer, por tarjeta
        self._area(card, [
            (self.combo_profile, ("vision", "detection", "profile")),
            (self.combo_engine, ("vision", "detection", "engine")),
            (self.spin_iou, ("vision", "detection", "iou_nms")),
            (self.combo_tracker, ("vision", "detection", "tracker")),
            (self.chk_nms_classes, ("vision", "detection", "class_agnostic_nms")),
        ])
        self._area(card_conf, [(spin, ("vision", "detection", key)) for key, spin in self.spin_confidences.items()]
                   + [(self.spin_min_area, ("vision", "detection", "min_area_pct"))])
        self._area(card_zone, [
            (self.chk_zone, ("vision", "zone", "active")),
            (self.chk_fixed, ("vision", "zone", "hide_fixed_objects")),
            (self.spin_fixed_s, ("vision", "zone", "fixed_object_s")),
        ])
        self._area(card_seg, [
            (self.spin_min_hits, ("vision", "tracking", "min_hits")),
            (self.spin_speed_interval, ("vision", "tracking", "speed_interval_s")),
            (self.spin_stopped, ("vision", "tracking", "stopped_speed_kmh")),
            (self.chk_boxes, ("vision", "display", "show_boxes")),
            (self.chk_class, ("vision", "display", "show_class")),
            (self.chk_speed, ("vision", "display", "show_speed")),
            (self.chk_trail, ("vision", "display", "show_trail")),
        ])
        return _page(card_hw, card, card_conf, card_zone, card_seg)

    def _section_calibration(self):
        """Crea la sección de calibración: modo, botones para marcar sobre el video y anchos de vehículos."""
        c = self.cfg.section("vision", "calibration")
        card = Card("Escala para medir la velocidad", "Convierte píxeles del video a metros reales")
        form = _form()
        self.combo_calibration = _list(_CALIBRATION, str(c.get("mode", "auto")))
        self.lbl_cal_state = QLabel("—")
        self.lbl_cal_state.setObjectName("valueHighlight")
        _row(form, "Modo", self.combo_calibration)
        _row(form, "Estado actual", self.lbl_cal_state)
        card.body.addLayout(form)
        card.body.addWidget(_help(
            "Plano (recomendado): marca sobre la calle las 4 esquinas de un rectángulo de medidas conocidas, "
            "por ejemplo el ancho del carril por el largo de una raya discontinua. Mide bien la velocidad en "
            "cualquier dirección, cerca o lejos de la cámara.\n"
            "Automática: aprende la escala con el ancho de los vehículos. Es aproximada: los vehículos que se "
            "acercan o alejan de la cámara salen más lentos de lo real. Se usa de respaldo mientras no marques el plano.\n"
            "Tramo: una sola escala para toda la imagen; solo sirve si la cámara mira la calle de frente. "
            "El tramo debe ser una distancia real pequeña (una raya del carril), no media pantalla."))
        # Botones para marcar plano o tramo sobre el video y para reiniciar el aprendizaje
        row = QHBoxLayout()
        btn_plane = _button("  Marcar plano de 4 puntos", "action_zone")
        btn_plane.clicked.connect(lambda: self.calibrate_on_video.emit(4))
        btn_mark = _button("  Marcar tramo", "action_ruler")
        btn_mark.clicked.connect(lambda: self.calibrate_on_video.emit(2))
        btn_reset = _button("  Reiniciar aprendizaje", "action_reset")
        btn_reset.clicked.connect(self.reset_calibration.emit)
        for button in (btn_plane, btn_mark, btn_reset):
            row.addWidget(button)
        row.addStretch(1)
        card.body.addLayout(row)

        # Anchos reales usados por la calibración automática
        card_widths = Card("Ancho real de los vehículos", "Usado por la calibración automática")
        form = _form()
        self.spin_car_width = _decimal(c.get("car_width_m", 1.8), 1.0, 3.0, " m")
        self.spin_moto_width = _decimal(c.get("motorcycle_width_m", 0.8), 0.4, 1.5, " m")
        self.spin_bus_width = _decimal(c.get("bus_width_m", 2.55), 1.5, 3.5, " m")
        self.spin_truck_width = _decimal(c.get("truck_width_m", 2.5), 1.5, 3.5, " m")
        self.spin_max_speed = _integer(c.get("max_speed_kmh", 160), 30, 300, " km/h")
        _row(form, "Automóvil", self.spin_car_width)
        _row(form, "Motocicleta", self.spin_moto_width)
        _row(form, "Autobús", self.spin_bus_width)
        _row(form, "Camión", self.spin_truck_width)
        _row(form, "Velocidad máxima válida", self.spin_max_speed)
        card_widths.body.addLayout(form)
        self._area(card, [(self.combo_calibration, ("vision", "calibration", "mode"))])
        self._area(card_widths, [
            (self.spin_car_width, ("vision", "calibration", "car_width_m")),
            (self.spin_moto_width, ("vision", "calibration", "motorcycle_width_m")),
            (self.spin_bus_width, ("vision", "calibration", "bus_width_m")),
            (self.spin_truck_width, ("vision", "calibration", "truck_width_m")),
            (self.spin_max_speed, ("vision", "calibration", "max_speed_kmh")),
        ])
        return _page(card, card_widths)

    def _section_stats(self):
        """Crea la sección de historial y alarmas (analytics.conf)."""
        cfg = self.cfg
        card = Card("Historial", "data/traffic_history.sqlite3")
        form = _form()
        self.spin_retention = _integer(cfg.get("analytics", "retention_days", default=180), 0, 3650, " días")
        _row(form, "Conservar datos", self.spin_retention, "0 = conservar para siempre")
        self.combo_refresh = _list(_UPDATES, cfg.get_text("analytics", "update_interval", "auto").strip().lower())
        _row(form, "Actualizar datos en vivo", self.combo_refresh,
              "Números de la cámara, recomendaciones, estadísticas y gráficas. "
              "En PCs poco potentes conviene un intervalo mayor")
        interval = update_interval_ms()
        card.body.addLayout(form)
        card.body.addWidget(_help(
            f"Automática usa el perfil de rendimiento: Bajo cada 3 s, Medio cada 2 s y Alto cada 1 s. "
            f"Ahora se actualiza {'en tiempo real' if interval < 1000 else f'cada {interval / 1000:g} s'}."))

        # Umbrales y retardos de las alarmas
        a = cfg.section("analytics", "alarms")
        card_alarms = Card("Alarmas", "Cuándo avisar en la campana de la barra superior")
        form = _form()
        self.spin_cong = _integer(a.get("congestion_pct", 75), 10, 100, " %")
        self.spin_cong_t = _integer(a.get("congestion_delay_s", 60), 0, 3600, " s")
        self.spin_queue = _integer(a.get("queue_vehicles", 6), 1, 100, " veh")
        self.spin_queue_t = _integer(a.get("queue_delay_s", 30), 0, 3600, " s")
        self.spin_video_t = _integer(a.get("no_video_delay_s", 10), 0, 600, " s")
        _row(form, "Congestión a partir de", self.spin_cong)
        _row(form, "…sostenida durante", self.spin_cong_t)
        _row(form, "Cola a partir de", self.spin_queue)
        _row(form, "…sostenida durante", self.spin_queue_t)
        _row(form, "Sin video durante", self.spin_video_t)
        card_alarms.body.addLayout(form)
        card_alarms.body.addWidget(_help("También se avisa al perder el enlace con el LOGO! y cuando está en STOP."))
        self._area(card, [
            (self.spin_retention, ("analytics", "history", "retention_days")),
            (self.combo_refresh, ("analytics", "general", "update_interval")),
        ])
        self._area(card_alarms, [
            (self.spin_cong, ("analytics", "alarms", "congestion_pct")),
            (self.spin_cong_t, ("analytics", "alarms", "congestion_delay_s")),
            (self.spin_queue, ("analytics", "alarms", "queue_vehicles")),
            (self.spin_queue_t, ("analytics", "alarms", "queue_delay_s")),
            (self.spin_video_t, ("analytics", "alarms", "no_video_delay_s")),
        ])
        return _page(card, card_alarms)

    def showEvent(self, event):
        """Ajusta la lista de secciones cuando ya tiene su estilo (y la escala) aplicado."""
        super().showEvent(event)
        self._fit_nav()

    def _fit_nav(self):
        """Deja la lista de secciones del alto justo de sus filas; si no cabe, se desplaza."""
        nav = self.nav
        rows = sum(nav.sizeHintForRow(r) for r in range(nav.count())) + nav.spacing() * nav.count()
        border = nav.height() - nav.viewport().height()   # bordes y relleno del CSS
        nav.setMaximumHeight(rows + max(0, border) + px(4))

    def _style_signature(self):
        """Devuelve el modo de tema y los tamaños de letra para saber si hay que recargar estilos."""
        cfg = self.cfg
        return (cfg.get_text("ui", "theme_mode", "auto"),
                tuple(str(cfg.section("ui", "fonts").get(key, "")) for key in FONT_DEFAULTS))

    def _section_appearance(self):
        """Crea la sección de tema, tamaños de letra, escala y el acceso a la carpeta de configuración."""
        card = Card("Tema", "Colores en app/config/theme.conf · estilos en app/ui/styles/")
        form = _form()
        self.combo_theme = _list(_THEMES, str(self.cfg.get_text("ui", "theme_mode", "auto")).lower())
        _row(form, "Modo", self.combo_theme)
        card.body.addLayout(form)
        card.body.addWidget(_help("Pulsa F5 en cualquier momento para recargar colores y estilos sin reiniciar."))

        # Botón para abrir la carpeta de configuración en el explorador
        card_files = Card("Archivos de configuración", str(CONFIG_DIR))
        btn = _button("  Abrir carpeta de configuración", "action_folder")
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_DIR))))
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch(1)
        card_files.body.addLayout(row)
        self._area(card, [(self.combo_theme, ("ui", "theme_mode"))])

        # Tamaño de cada tipo de letra (se aplica al guardar, sin reiniciar)
        card_fonts = Card("Tamaño de letra", "Puntos (pt) con la escala al 100 % · ui.conf [fonts]")
        form_fonts = _form()
        font_fields = []
        for key, label, tip in _FONTS:
            value = self.cfg.get("ui", "fonts", key, default=FONT_DEFAULTS[key])
            spin = _decimal(value, 5, 40, " pt", step=0.5, decimals=1)
            _row(form_fonts, label, spin, tip)
            font_fields.append((spin, ("ui", "fonts", key)))
        card_fonts.body.addLayout(form_fonts)
        card_fonts.body.addWidget(_help("Cada elemento conserva su proporción dentro de su grupo. "
                                        "Los cambios se ven al pulsar «Guardar cambios»."))
        self._area(card_fonts, font_fields)

        # Escala general de la interfaz (medidas, tarjetas, iconos y letras)
        card_scale = Card("Escala de la interfaz", "Se adapta al tamaño de la pantalla · ui.conf [window] scale")
        form_scale = _form()
        self.combo_scale = _list(_SCALES, self.cfg.get_text("ui", "scale", "auto").strip().lower())
        _row(form_scale, "Escala", self.combo_scale)
        card_scale.body.addLayout(form_scale)
        card_scale.body.addWidget(_help(
            f"En esta pantalla se usa {layout_factor() * 100:.0f} % para medidas y {font_factor() * 100:.0f} % "
            "para letras. 100 % equivale a una pantalla de 1920×1080. El cambio se aplica al reiniciar la app."))
        self._area(card_scale, [(self.combo_scale, ("ui", "window", "scale"))])
        return _page(card, card_fonts, card_scale, card_files)

    # --- Utilidades ---

    def _browse_row(self, field, icon, action):
        """Devuelve una fila con el campo y un botón Examinar que ejecuta la acción dada."""
        button = _button("", icon, "icon", "soft_text")
        button.setToolTip("Examinar…")
        button.clicked.connect(action)
        row = QHBoxLayout()
        row.addWidget(field, stretch=1)
        row.addWidget(button)
        return row

    def _load_cameras(self):
        """Llena la lista con las cámaras detectadas y selecciona la configurada."""
        self.combo_cameras.clear()
        selection = int(self.cfg.get("camera", "device_index", default=0))
        for index, name in list_camera_devices():
            self.combo_cameras.addItem(f"[{index}] {name}", index)
        if self.combo_cameras.count() == 0:
            self.combo_cameras.addItem("No se detectaron cámaras", selection)
        index = self.combo_cameras.findData(selection)
        self.combo_cameras.setCurrentIndex(max(0, index))

    def _browse_video(self):
        """Pide un archivo de video de prueba y lo pone en su campo."""
        path, _ = QFileDialog.getOpenFileName(self, "Video de prueba", "", "Videos (*.mp4 *.avi *.mkv *.mov *.webm)")
        if path:
            self.txt_video.setText(path)

    def _browse_folder(self):
        """Pide la carpeta de grabaciones y la pone en su campo."""
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de grabaciones")
        if folder:
            self.txt_folder.setText(folder)

    # --- API usada por la ventana principal ---

    def set_zone_active(self, active):
        """Marca o desmarca la casilla de zona activa."""
        self.chk_zone.setChecked(bool(active))

    def set_calibration_mode(self, mode):
        """Selecciona el modo de calibración indicado."""
        index = self.combo_calibration.findData(mode)
        if index >= 0:
            self.combo_calibration.setCurrentIndex(index)

    def set_calibration_state(self, text):
        """Muestra el estado actual de la calibración."""
        self.lbl_cal_state.setText(text)

    def save_all(self):
        """Guarda todos los campos en los .conf y avisa; recarga el tema si el modo cambio."""
        cfg = self.cfg
        previous_style = self._style_signature()
        # Guarda cada campo de todas las áreas y la cámara elegida
        for _, fields, _ in self._areas:
            for field in fields:
                cfg.set(*field.target, field.read_frame())
        self._save_camera()

        _flash(self.btn_save, "  Guardado", "action_check", "on_accent",
               "  Guardar cambios", "action_save", "on_accent")
        self.settings_saved.emit()
        if self._style_signature() != previous_style:
            self.theme_changed.emit()
            QTimer.singleShot(0, self._fit_nav)
