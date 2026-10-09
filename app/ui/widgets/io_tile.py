import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from ...core.formatting import format_duration
from ..styles.theme import set_prop
from ..scale import px, tx


class IoTile(QFrame):
    """Tarjeta de una señal digital del Logo (Q1, I3...) con LED, nombre, estado y cronómetro.

    Las señales salen de app/config/io.conf; estilos en app/ui/styles/widgets/io_tile.css.
    """

    def __init__(self, signal, parent=None):
        """Crea la tarjeta para la señal indicada, apagada y con el cronómetro en cero."""
        super().__init__(parent)
        self.signal = signal
        self.active = False
        self._start = None
        self._last = 0.0

        # Propiedades para el CSS: color de la señal y estado activo
        self.setObjectName("ioTile")
        self.setProperty("signal", signal.color)
        self.setProperty("active", False)
        self.setMinimumHeight(tx(54))   # crece si se agranda la letra
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{signal.code} · {signal.name} (bit {signal.bit})")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(px(12), px(8), px(12), px(8))
        layout.setSpacing(px(10))

        self.led = QLabel()
        self.led.setObjectName("ioLed")
        self.led.setFixedSize(tx(10), tx(10))
        layout.addWidget(self.led, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Código y nombre de la señal
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.lbl_code = QLabel(signal.code)
        self.lbl_code.setObjectName("ioCode")
        self.lbl_name = QLabel(signal.name)
        self.lbl_name.setObjectName("ioName")
        texts.addWidget(self.lbl_code)
        texts.addWidget(self.lbl_name)
        layout.addLayout(texts, stretch=1)

        # Estado ON/OFF y tiempo encendido a la derecha
        side = QVBoxLayout()
        side.setSpacing(0)
        self.lbl_state = QLabel("OFF")
        self.lbl_state.setObjectName("ioState")
        self.lbl_state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_time = QLabel("")
        self.lbl_time.setObjectName("ioTime")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        side.addWidget(self.lbl_state)
        side.addWidget(self.lbl_time)
        layout.addLayout(side)

    def update_state(self, active):
        """Actualiza el estado y, si la señal usa cronómetro, el tiempo que lleva encendida."""
        active = bool(active)
        # Cronómetro: al apagarse conserva el último tiempo medido
        if self.signal.stopwatch:
            now = time.monotonic()
            if active:
                if self._start is None:
                    self._start = now
                self._last = now - self._start
            else:
                self._start = None
            self.lbl_time.setText(format_duration(self._last))

        if active != self.active:
            self.active = active
            self.lbl_state.setText("ON" if active else "OFF")
            set_prop(self, "active", active)

    def reset(self):
        """Pone el cronómetro en cero y deja la tarjeta apagada."""
        self._start = None
        self._last = 0.0
        self.lbl_time.setText("")
        self.active = True  # fuerza el refresco
        self.update_state(False)
