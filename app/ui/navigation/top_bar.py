from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from ...core.app_config import AppConfig
from ..components import StatusChip, icons
from ..scale import px, tx

# Estado de conexión -> (tipo de chip, texto del botón, variant del botón, icono)
_STATES = {
    "disconnected": ("neutral", "Conectar", "primary", "action_plug"),
    "connecting": ("info", "Cancelar", "secondary", "action_unplug"),
    "reconnecting": ("warning", "Cancelar", "secondary", "action_unplug"),
    "connected": ("success", "Desconectar", "danger", "action_unplug"),
    "error": ("error", "Reintentar", "primary", "action_plug"),
}


class TopBar(QFrame):
    """Barra superior con título de la página, estados del PLC y del circuito, IP y conexión.

    Estilos en app/ui/styles/layout/top_bar.css.
    """

    connect_clicked = pyqtSignal(str)   # ip
    alarms_clicked = pyqtSignal()
    ip_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        """Crea el título, el botón de alarmas, los chips de estado, el campo de IP y el botón de conexión."""
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(tx(AppConfig.get_instance().get("ui", "top_bar_height", default=60)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(px(24), 0, px(20), 0)
        layout.setSpacing(px(10))

        # Título de la página actual
        self.lbl_page = QLabel("Semáforo")
        self.lbl_page.setObjectName("topTitle")
        layout.addWidget(self.lbl_page)
        layout.addStretch(1)

        # Botón de alarmas con contador e icono según la severidad
        self.btn_alarms = QPushButton()
        self.btn_alarms.setObjectName("btnAlarms")
        self.btn_alarms.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_alarms.setToolTip("Alarmas")
        self.btn_alarms.setIconSize(QSize(tx(18), tx(18)))
        self.btn_alarms.clicked.connect(self.alarms_clicked.emit)
        layout.addWidget(self.btn_alarms)
        self._severity = None
        icons.record(self, self._refresh_alarms, label="alarms")

        # Chips de estado del circuito y del PLC
        self.chip_circuit = StatusChip("Circuito", "En espera", "neutral")
        layout.addWidget(self.chip_circuit)
        self.chip_plc = StatusChip("PLC", "Desconectado", "neutral")
        layout.addWidget(self.chip_plc)

        self.separator = QFrame()
        self.separator.setObjectName("topSeparator")
        self.separator.setFixedSize(1, tx(26))
        layout.addWidget(self.separator)

        # Campo de IP del Logo (Enter conecta)
        self.txt_ip = QLineEdit(AppConfig.get_instance().get_text("plc", "ip", "192.168.0.3"))
        self.txt_ip.setObjectName("ipField")
        self.txt_ip.setPlaceholderText("IP del LOGO!")
        self.txt_ip.setFixedWidth(tx(130))
        self.txt_ip.setToolTip("Dirección IP del LOGO! (Enter para conectar)")
        self.txt_ip.editingFinished.connect(lambda: self.ip_changed.emit(self.ip()))
        self.txt_ip.returnPressed.connect(self._on_connect)
        layout.addWidget(self.txt_ip)

        # Botón de conexión: texto, variant e icono cambian según el estado
        self.btn_connect = QPushButton("Conectar")
        self.btn_connect.setObjectName("btnConnect")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setMinimumWidth(tx(128))
        self.btn_connect.setIconSize(QSize(tx(16), tx(16)))
        self.btn_connect.clicked.connect(self._on_connect)
        layout.addWidget(self.btn_connect)
        self._state = "disconnected"
        self._level = 0          # 0 completa · 1 sin etiquetas · 2 botón solo icono · 3 chips solo con el punto
        icons.record(self, self._refresh_button)
        self.set_connection_state("disconnected", "Desconectado")

    # --- Estado mostrado ---

    def ip(self):
        """Devuelve la IP escrita, sin espacios."""
        return self.txt_ip.text().strip()

    def set_ip(self, ip):
        """Escribe la IP en el campo solo si es distinta de la actual."""
        if self.txt_ip.text() != ip:
            self.txt_ip.setText(ip)

    def set_title(self, text):
        """Cambia el título de la página."""
        self.lbl_page.setText(text)
        self._fit()

    def set_connection_state(self, state, text):
        """Actualiza el chip del PLC y el botón; la IP solo se edita desconectado o con error."""
        self._state = state
        self.chip_plc.set_state(_STATES.get(state, _STATES["error"])[0], text)
        self._level = -1   # el texto cambio: se vuelve a medir desde el nivel completo
        self.txt_ip.setEnabled(state in ("disconnected", "error"))
        self._refresh_button()
        self._fit()

    def set_circuit_state(self, kind, text):
        """Actualiza el chip del circuito con el tipo de estado y el texto."""
        self.chip_circuit.set_state(kind, text)
        self._fit()

    def _refresh_button(self):
        """Aplica al botón de conexión el texto, la variant y el icono del estado actual."""
        _, text, variant, icon = _STATES.get(self._state, _STATES["error"])
        # En ventanas angostas el botón queda solo con el icono y el texto pasa a la ayuda
        compact = self._level >= 2
        self.btn_connect.setText("" if compact else f"  {text}")
        self.btn_connect.setToolTip(text if compact else "")
        self.btn_connect.setMinimumWidth(0 if compact else tx(128))
        self.btn_connect.setProperty("variant", variant)
        color = "text" if variant == "secondary" else "on_accent"
        self.btn_connect.setIcon(icons.icon(icon, color, 16))
        self.btn_connect.style().unpolish(self.btn_connect)
        self.btn_connect.style().polish(self.btn_connect)

    # --- Adaptacion al ancho ---

    def _compact(self, level):
        """Aplica un nivel de compactacion para que nada se corte ni se encime.

        1 oculta las etiquetas de los chips, 2 deja el botón solo con icono y 3 deja los
        chips solo con su punto de color (el texto queda en la ayuda) y angosta la IP.
        """
        if level == self._level:
            return
        self._level = level
        for chip in (self.chip_circuit, self.chip_plc):
            chip.lbl_label.setVisible(level < 1)
            chip.lbl_text.setVisible(level < 3)
        self.txt_ip.setFixedWidth(tx(130 if level < 3 else 110))
        self.separator.setVisible(level < 2)
        self._refresh_button()

    def resizeEvent(self, event):
        """Recalcula la compactacion al cambiar el ancho."""
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        """Usa el nivel más completo que quepa; se llama al cambiar el ancho o cualquier texto."""
        for level in range(4):
            self._compact(level)
            self.layout().invalidate()
            if self.layout().sizeHint().width() <= self.width():
                break

    def minimumSizeHint(self):
        """Permite que la ventana se angoste; la barra se compacta sola."""
        return QSize(px(320), super().minimumSizeHint().height())

    # --- Alarmas ---

    def set_alarms(self, count, severity):
        """Muestra la cantidad de alarmas sin reconocer y la severidad máxima activa (None si no hay)."""
        self._severity = severity
        self.btn_alarms.setText(f" {count}" if count else "")
        self.btn_alarms.setProperty("severity", severity or "")
        self.btn_alarms.setToolTip(f"{count} alarma(s) sin reconocer" if count else "Alarmas")
        self.btn_alarms.style().unpolish(self.btn_alarms)
        self.btn_alarms.style().polish(self.btn_alarms)
        self._refresh_alarms()

    def _refresh_alarms(self):
        """Pinta el icono de la campana con el color de la severidad."""
        colors = {"critical": "error", "warning": "warning", "info": "info"}
        self.btn_alarms.setIcon(icons.icon("status_bell", colors.get(self._severity, "soft_text"), 18))

    def _on_connect(self):
        """Emite connect_clicked con la IP escrita."""
        self.connect_clicked.emit(self.ip())
