from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..scale import px
from .responsive import fit_header


class Card(QFrame):
    """Tarjeta (panel) con encabezado opcional, bloque visual básico de toda la interfaz.

    El contenido se agrega en card.body y los botones del encabezado con add_action().
    Estilos en app/ui/styles/components/card.css.
    """

    def __init__(self, title=None, subtitle=None, parent=None, margin=16, spacing=12):
        """Crea la tarjeta con título, subtitulo y zona de acciones si se indica título."""
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        margin, spacing = px(margin), px(spacing)
        layout.setContentsMargins(margin, margin - px(2), margin, margin)
        layout.setSpacing(spacing)

        # Encabezado: textos a la izquierda y acciones a la derecha
        self._actions = None
        if title:
            header = QHBoxLayout()
            header.setSpacing(px(8))
            texts = QVBoxLayout()
            texts.setSpacing(px(1))
            self.lbl_title = QLabel(title)
            self.lbl_title.setObjectName("cardTitle")
            texts.addWidget(self.lbl_title)
            if subtitle:
                self.lbl_subtitle = QLabel(subtitle)
                self.lbl_subtitle.setObjectName("cardSubtitle")
                texts.addWidget(self.lbl_subtitle)
            header.addLayout(texts, stretch=1)
            self._actions = QHBoxLayout()
            self._actions.setSpacing(px(6))
            header.addLayout(self._actions)
            layout.addLayout(header)

        # Cuerpo donde se agrega el contenido
        self.body = QVBoxLayout()
        self.body.setSpacing(spacing)
        layout.addLayout(self.body, stretch=1)

    def add_action(self, widget):
        """Agrega un widget a las acciones del encabezado y lo devuelve."""
        if self._actions is not None:
            self._actions.addWidget(widget)
        return widget


class PageHeader(QWidget):
    """Encabezado de página con título y descripción a la izquierda y acciones a la derecha."""

    def __init__(self, title, description="", parent=None):
        """Crea el encabezado con el título y la descripción opcional."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(8))

        # Título y descripción
        texts = QVBoxLayout()
        texts.setSpacing(px(2))
        lbl_title = QLabel(title)
        lbl_title.setObjectName("pageTitle")
        texts.addWidget(lbl_title)
        if description:
            lbl_desc = QLabel(description)
            lbl_desc.setObjectName("pageDescription")
            lbl_desc.setWordWrap(True)   # en ventanas angostas baja de línea en lugar de ensanchar la página
            texts.addWidget(lbl_desc)
        layout.addLayout(texts, stretch=1)
        self._texts = texts

        # Zona de acciones; el espacio final las mantiene a la izquierda cuando bajan de línea
        self._actions = QHBoxLayout()
        self._actions.setSpacing(px(8))
        self._actions.addStretch(1)
        layout.addLayout(self._actions)

    def add_action(self, widget):
        """Agrega un widget a las acciones de la derecha y lo devuelve."""
        self._actions.insertWidget(self._actions.count() - 1, widget)
        return widget

    def resizeEvent(self, event):
        """Si título y botones no caben en una fila, baja los botones debajo del título."""
        super().resizeEvent(event)
        fit_header(self, self._texts, self._actions)

    def minimumSizeHint(self):
        """Permite angostarse hasta lo que pida el más ancho entre título y botones."""
        width = max(self._texts.minimumSize().width(), self._actions.sizeHint().width())
        return QSize(width, self.layout().minimumSize().height())
