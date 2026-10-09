from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from ..scale import px, tx
from ..styles.theme import set_prop
from . import icons


class StatCard(QFrame):
    """Tarjeta de indicador (KPI) con icono, etiqueta, valor grande, unidad y barra opcional.

    Tonos: accent, success, warning, error y text. Estilos en
    app/ui/styles/components/stat_card.css.
    """

    def __init__(self, label, icon=None, tone="accent", unit="", with_bar=False, compact=False, parent=None):
        """Crea la tarjeta con su etiqueta, icono, tono, unidad y barra opcional.

        compact la hace más baja y con el valor más pequeño (por ejemplo, debajo del video).
        """
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setProperty("compact", compact)
        self._icon = icon
        self._tone = tone
        self._icon_size = 15 if compact else 18

        layout = QVBoxLayout(self)
        if compact:
            layout.setContentsMargins(px(12), px(9), px(12), px(9))
            layout.setSpacing(px(3))
        else:
            layout.setContentsMargins(px(16), px(14), px(16), px(14))
            layout.setSpacing(px(6))

        # Fila superior: icono y etiqueta
        row = QHBoxLayout()
        row.setSpacing(px(8))
        if icon:
            self.lbl_icon = QLabel()
            self.lbl_icon.setObjectName("statIcon")
            side = tx(24 if compact else 30)
            self.lbl_icon.setFixedSize(side, side)
            self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(self.lbl_icon)
            icons.record(self, self._paint_icon)
        self.lbl_label = QLabel(label)
        self.lbl_label.setObjectName("statLabel")
        self.lbl_label.setWordWrap(True)   # en tarjetas angostas baja de línea en lugar de ensanchar
        row.addWidget(self.lbl_label, stretch=1)
        layout.addLayout(row)

        # Valor grande con su unidad
        values = QHBoxLayout()
        values.setSpacing(px(6))
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("statValue")
        values.addWidget(self.lbl_value, alignment=Qt.AlignmentFlag.AlignBottom)
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setObjectName("statUnit")
        values.addWidget(self.lbl_unit, alignment=Qt.AlignmentFlag.AlignBottom)
        values.addStretch(1)
        layout.addLayout(values)

        # Detalle y barra opcional (rango 0-1000 para mayor resolución)
        self.lbl_detail = QLabel("")
        self.lbl_detail.setObjectName("statDetail")
        self.lbl_detail.setWordWrap(True)
        layout.addWidget(self.lbl_detail)

        self.bar = None
        if with_bar:
            self.bar = QProgressBar()
            self.bar.setObjectName("statBar")
            self.bar.setTextVisible(False)
            self.bar.setRange(0, 1000)
            self.bar.setFixedHeight(px(6))
            layout.addWidget(self.bar)

        self.set_tone(tone)

    def _paint_icon(self):
        """Pinta el icono con el color del tono actual."""
        if self._icon:
            self.lbl_icon.setPixmap(icons.icon_pixmap(self._icon, self._tone_color(), self._icon_size))

    def _tone_color(self):
        """Devuelve la clave de la paleta que corresponde al tono (accent si no se reconoce)."""
        return {"accent": "accent", "success": "success", "warning": "warning",
                "error": "error", "text": "text"}.get(self._tone, "accent")

    def set_tone(self, tone):
        """Cambia el tono de la tarjeta (propiedad tone del CSS) y el color del icono."""
        self._tone = tone
        set_prop(self, "tone", tone)
        self._paint_icon()

    def set_value(self, value, detail=None, fraction=None):
        """Muestra el valor, el detalle opcional y la fracción (0 a 1) en la barra."""
        self.lbl_value.setText(str(value))
        if detail is not None:
            self.lbl_detail.setText(detail)
        if self.bar is not None and fraction is not None:
            self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
