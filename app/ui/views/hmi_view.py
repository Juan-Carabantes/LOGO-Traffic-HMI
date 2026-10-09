from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ...core.io_map import load_signals, layout_io
from ..components import AdaptiveRow, Card, ResponsiveGrid, StatusChip, icons
from ..widgets.io_tile import IoTile
from ..widgets.traffic_light import TrafficLightWidget
from ..scale import px, tx

MAX_LOG_LINES = 2000

# Botones de control: (orden, texto, marca del Logo, icono, color)
_CONTROLS = (
    ("start", "Marcha", "M1", "action_play", "green"),
    ("stop", "Paro", "M2", "action_stop", "red"),
    ("pedestrian", "Peatón", "M3", "action_walk", "blue"),
)


class HmiView(QWidget):
    """Vista principal: semáforo, entradas/salidas, control remoto y registro de eventos.

    Los estilos están en app/ui/styles/views/hmi_view.css y las señales de E/S
    se definen en app/config/io.conf.
    """

    control_requested = pyqtSignal(str)       # 'start' | 'stop' | 'pedestrian'

    def __init__(self, parent=None):
        """Arma el panel del semáforo a la izquierda y E/S, control y registro a la derecha."""
        super().__init__(parent)
        self.tiles = {}
        self.control_buttons = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(px(24), px(20), px(24), px(24))
        # Semáforo a la izquierda y paneles a la derecha; en ventanas angostas se apilan
        root = AdaptiveRow(breakpoint=760)
        outer.addWidget(root)
        root.add(self._create_light_panel(), stretch=4)

        # Columna derecha: E/S, control remoto y registro
        column = QWidget()
        right = QVBoxLayout(column)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(px(16))
        right.addWidget(self._create_io_panel())
        right.addWidget(self._create_control_panel())
        right.addWidget(self._create_log_panel(), stretch=1)
        root.add(column, stretch=6)

    # --- Paneles ---

    def _create_light_panel(self):
        """Crea la tarjeta con el semáforo y el indicador de estado del circuito."""
        card = Card("Semáforo", "Estado reportado por el LOGO!")
        card.setMinimumWidth(tx(200))
        self.chip_circuit = StatusChip("", "En espera", "neutral")
        card.add_action(self.chip_circuit)

        self.traffic_light = TrafficLightWidget()
        card.body.addWidget(self.traffic_light, stretch=1)
        return card

    def _create_io_panel(self):
        """Crea la tarjeta con una cuadricula de salidas y otra de entradas según io.conf."""
        card = Card("Entradas y salidas", "Señales digitales del LOGO! (app/config/io.conf)")
        layout = layout_io()
        outputs, inputs = load_signals(only_visible=True)
        groups = (
            (outputs, layout["outputs_title"], layout["output_columns"]),
            (inputs, layout["inputs_title"], layout["input_columns"]),
        )
        # Un título y una cuadricula por grupo; los grupos vacios se omiten
        for signals, title, columns in groups:
            if not signals:
                continue
            label = QLabel(title.upper())
            label.setObjectName("groupLabel")
            card.body.addWidget(label)
            # Hasta las columnas de io.conf; si no caben, menos columnas y más filas
            grid = ResponsiveGrid(max_columns=columns, spacing=8)
            for signal in signals:
                tile = IoTile(signal)
                self.tiles[signal.code] = tile
                grid.add_widget(tile)
            card.body.addWidget(grid)
        return card

    def _create_control_panel(self):
        """Crea los botones de Marcha, Paro y Peatón, deshabilitados hasta conectar el Logo."""
        card = Card("Control remoto", "Pulsos por Ethernet a las marcas M1–M3")
        # Los botones bajan de línea si la columna es angosta
        row = ResponsiveGrid(spacing=10)
        for key, text, marker, icon, signal in _CONTROLS:
            button = QPushButton(f"  {text}  ·  {marker}")
            button.setProperty("variant", "control")
            button.setProperty("signal", signal)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setEnabled(False)
            button.setToolTip("Conecta el LOGO! para habilitar el control")
            button.clicked.connect(lambda _=False, c=key: self.control_requested.emit(c))
            icons.apply(button, icon, f"signal_{signal}", 16)
            row.add_widget(button)
            self.control_buttons.append(button)
        card.body.addWidget(row)
        return card

    def _create_log_panel(self):
        """Crea el registro de eventos con un botón para limpiarlo."""
        card = Card("Registro de eventos", "Tramas S7, cámara y sistema")
        btn_clear = QPushButton()
        btn_clear.setProperty("variant", "icon")
        btn_clear.setToolTip("Limpiar registro")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        icons.apply(btn_clear, "action_trash", "soft_text", 16)
        card.add_action(btn_clear)

        # Registro de solo lectura, sin ajuste de línea y limitado a MAX_LOG_LINES
        self.txt_log = QPlainTextEdit()
        self.txt_log.setObjectName("eventLog")
        self.txt_log.setReadOnly(True)
        self.txt_log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.txt_log.setMaximumBlockCount(MAX_LOG_LINES)
        self.txt_log.setMinimumHeight(tx(110))
        btn_clear.clicked.connect(self.txt_log.clear)
        card.body.addWidget(self.txt_log)
        return card

    # --- API usada por la ventana principal ---

    def add_log(self, text):
        """Agrega una línea al registro con la hora actual."""
        hour = datetime.now().strftime("%H:%M:%S")
        self.txt_log.appendPlainText(f"{hour}  {text}")

    def update_io(self, bits_q, bits_i):
        """Actualiza cada indicador con su bit de salidas (Q) o entradas (I)."""
        for tile in self.tiles.values():
            bits = bits_q if tile.signal.is_output else bits_i
            tile.update_state(tile.signal.bit < len(bits) and bits[tile.signal.bit])

    def io_off(self):
        """Apaga todos los indicadores de E/S."""
        for tile in self.tiles.values():
            tile.reset()

    def set_circuit_state(self, kind, text):
        """Muestra el estado del circuito en el indicador del semáforo."""
        self.chip_circuit.set_state(kind, text)

    def set_controls_enabled(self, enabled):
        """Habilita o deshabilita los botones de control y ajusta su ayuda."""
        for button in self.control_buttons:
            button.setEnabled(enabled)
            button.setToolTip("" if enabled else "Conecta el LOGO! para habilitar el control")
