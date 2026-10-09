from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton
from ..scale import px


class SegmentedControl(QFrame):
    """Control segmentado: grupo de botones exclusivos, como [ Hoy | 7 días | 30 días ].

    Estilos en app/ui/styles/components/segmented.css.
    """

    changed = pyqtSignal(str)   # clave de la opción elegida

    def __init__(self, options, selection=None, parent=None):
        """Crea un botón por opción; options es [(clave, texto), ...] y selection la clave inicial."""
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(px(3), px(3), px(3), px(3))
        layout.setSpacing(px(2))
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._keys = []
        for index, (key, text) in enumerate(options):
            button = QPushButton(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button, index)
            self._keys.append(key)
            layout.addWidget(button)
        index = self._keys.index(selection) if selection in self._keys else 0
        self._group.button(index).setChecked(True)
        self._group.idClicked.connect(lambda i: self.changed.emit(self._keys[i]))

    def value(self):
        """Devuelve la clave de la opción seleccionada."""
        return self._keys[self._group.checkedId()]
