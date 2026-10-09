from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

from ..scale import px, tx
from ..styles.theme import set_prop


class StatusChip(QFrame):
    """Chip de estado con punto de color, etiqueta y texto (por ejemplo: PLC  S7 activo).

    Estados: success, warning, error, neutral e info. Estilos en
    app/ui/styles/components/status_chip.css.
    """

    def __init__(self, label="", text="", state="neutral", parent=None):
        """Crea el chip con la etiqueta opcional, el texto y el estado inicial."""
        super().__init__(parent)
        self.setObjectName("statusChip")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(px(10), px(5), px(12), px(5))
        layout.setSpacing(px(7))

        # Punto de color, etiqueta y texto
        self.point = QLabel()
        self.point.setObjectName("chipDot")
        self.point.setFixedSize(tx(8), tx(8))
        layout.addWidget(self.point)

        if label:
            self.lbl_label = QLabel(label)
            self.lbl_label.setObjectName("chipLabel")
            layout.addWidget(self.lbl_label)

        self.lbl_text = QLabel(text)
        self.lbl_text.setObjectName("chipText")
        layout.addWidget(self.lbl_text)
        self.set_state(state, text)

    def set_state(self, state, text=None):
        """Cambia el estado (propiedad state del CSS) y, si se indica, el texto."""
        if text is not None:
            self.lbl_text.setText(text)
        # La ayuda repite el contenido por si la etiqueta se oculta en ventanas angostas
        label = self.lbl_label.text() + ": " if getattr(self, "lbl_label", None) else ""
        self.setToolTip(label + self.lbl_text.text())
        set_prop(self, "state", state)
