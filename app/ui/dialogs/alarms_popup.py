from datetime import datetime

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from ..scale import px, tx

_SEVERITY_NAME = {"critical": "Crítica", "warning": "Aviso", "info": "Info"}


def _row(text, detail, severity, active):
    """Crea la fila de una alarma con punto de color, texto y detalle."""
    row = QFrame()
    row.setObjectName("alarmRow")
    row.setProperty("severity", severity)
    row.setProperty("active", active)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(px(10), px(8), px(10), px(8))
    layout.setSpacing(px(10))
    point = QLabel()
    point.setObjectName("alarmDot")
    point.setFixedSize(tx(8), tx(8))
    layout.addWidget(point, alignment=Qt.AlignmentFlag.AlignTop)
    texts = QVBoxLayout()
    texts.setSpacing(px(2))
    lbl = QLabel(text)
    lbl.setObjectName("alarmText")
    lbl.setWordWrap(True)
    sub = QLabel(detail)
    sub.setObjectName("alarmDetail")
    texts.addWidget(lbl)
    texts.addWidget(sub)
    layout.addLayout(texts, stretch=1)
    return row


class AlarmsPopup(QFrame):
    """Panel desplegable con las alarmas activas y el historial reciente.

    Estilos en app/ui/styles/dialogs/alarms_popup.css.
    """

    def __init__(self, alarms, history, parent=None):
        """Crea el panel con las alarmas activas de alarms y las cerradas de history."""
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("alarmsPopup")
        self.setFixedWidth(tx(380))
        self.alarms = alarms

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(14), px(12), px(14), px(12))
        layout.setSpacing(px(10))

        # Encabezado con el botón para reconocer todas
        header_view = QHBoxLayout()
        title = QLabel("Alarmas")
        title.setObjectName("cardTitle")
        header_view.addWidget(title, stretch=1)
        button = QPushButton("Reconocer todas")
        button.setProperty("variant", "ghost")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setEnabled(bool(alarms.active))
        button.clicked.connect(self._ack)
        header_view.addWidget(button)
        layout.addLayout(header_view)

        # Lista desplazable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumHeight(tx(420))
        container = QWidget()
        ready = QVBoxLayout(container)
        ready.setContentsMargins(0, 0, 0, 0)
        ready.setSpacing(px(6))

        # Alarmas activas, de la más reciente a la más antigua
        section = QLabel("ACTIVAS")
        section.setObjectName("groupLabel")
        ready.addWidget(section)
        if alarms.active:
            for alarm in sorted(alarms.active.values(), key=lambda a: a.start, reverse=True):
                detail = f"{_SEVERITY_NAME.get(alarm.severity)} · desde {datetime.fromtimestamp(alarm.start):%H:%M:%S}"
                if alarm.acked:
                    detail += " · reconocida"
                ready.addWidget(_row(alarm.text, detail, alarm.severity, True))
        else:
            empty = QLabel("Sin alarmas activas ✓")
            empty.setObjectName("helpText")
            ready.addWidget(empty)

        # Historial: hasta 10 alarmas ya cerradas con su duración
        recent = history.recent_alarms(15) if history is not None else []
        closed = [r for r in recent if r[1] is not None]
        if closed:
            section = QLabel("HISTORIAL")
            section.setObjectName("groupLabel")
            ready.addWidget(section)
            for start, end, _code, severity, text in closed[:10]:
                duration = int(end - start)
                detail = f"{datetime.fromtimestamp(start):%d/%m %H:%M} · duró {duration // 60} min {duration % 60} s"
                ready.addWidget(_row(text, detail, severity, False))
        ready.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _ack(self):
        """Reconoce todas las alarmas activas y cierra el panel."""
        self.alarms.ack_all()
        self.close()

    def show_below(self, widget):
        """Muestra el panel debajo del widget, alineado a su borde derecho."""
        self.adjustSize()
        point = widget.mapToGlobal(QPoint(widget.width() - self.width(), widget.height() + 6))
        self.move(point)
        self.show()
