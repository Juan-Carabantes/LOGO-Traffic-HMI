from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QBoxLayout, QGridLayout, QLayout, QSizePolicy, QWidget

from ..scale import px


# --- Distribucion que pasa a la siguiente línea ---

class FlowLayout(QLayout):
    """Acomoda los widgets en fila y pasa a la siguiente línea cuando ya no caben.

    Se usa para grupos de indicadores pequeños (chips) que en una ventana angosta
    se apilan en lugar de forzar un desplazamiento horizontal.
    """

    def __init__(self, parent=None, spacing=8):
        """Crea la distribucion vacía con el espacio indicado entre elementos."""
        super().__init__(parent)
        self._items = []
        self._space = px(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        """Agrega un elemento al final (Qt lo llama desde addWidget)."""
        self._items.append(item)

    def count(self):
        """Devuelve la cantidad de elementos."""
        return len(self._items)

    def itemAt(self, index):
        """Devuelve el elemento de la posición indicada o None."""
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        """Quita y devuelve el elemento de la posición indicada."""
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        """No se expande por si misma; ocupa lo que necesitan sus elementos."""
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        """El alto depende del ancho disponible (más líneas si es angosto)."""
        return True

    def heightForWidth(self, width):
        """Calcula el alto necesario para el ancho dado sin mover nada."""
        return self._arrange(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect):
        """Acomoda los elementos dentro del rectangulo asignado."""
        super().setGeometry(rect)
        self._arrange(rect, move=True)

    def sizeHint(self):
        """Tamaño ideal: todos los elementos en una sola fila."""
        width = sum(i.sizeHint().width() for i in self._items) + self._space * max(0, len(self._items) - 1)
        height = max((i.sizeHint().height() for i in self._items), default=0)
        return QSize(width, height)

    def minimumSize(self):
        """Tamaño mínimo: el elemento más ancho (todos apilados)."""
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect, move):
        """Ubica cada elemento de izquierda a derecha y devuelve el alto usado."""
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            # Si no cabe en la línea actual, pasa a la siguiente
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x = rect.x()
                y += line_height + self._space
                line_height = 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._space
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


# --- Cuadricula que ajusta sus columnas al ancho ---

class ResponsiveGrid(QWidget):
    """Cuadricula de tarjetas que reduce sus columnas cuando la ventana se angosta.

    Con espacio suficiente muestra todas en una fila (o hasta max_columns); si no caben,
    usa menos columnas y agrega filas, sin encimar tarjetas ni forzar desplazamiento
    horizontal. Todas las columnas tienen el mismo ancho.
    """

    def __init__(self, widgets=(), max_columns=None, spacing=12, parent=None):
        """Crea la cuadricula con los widgets dados y el máximo de columnas (por defecto, todos)."""
        super().__init__(parent)
        self._widgets = []
        self._max_columns = max_columns
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(px(spacing))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._height = 0
        for widget in widgets:
            self.add_widget(widget)

    def add_widget(self, widget):
        """Agrega una tarjeta al final y vuelve a acomodar."""
        self._widgets.append(widget)
        self._columns = 0
        self._reflow(self.width() or 10_000)
        return widget

    def _item_width(self):
        """Ancho mínimo que necesita la tarjeta más exigente."""
        return max((w.minimumSizeHint().width() for w in self._widgets), default=1)

    def _columns_for(self, width):
        """Cantidad de columnas que caben en el ancho dado."""
        total = len(self._widgets)
        limit = min(total, self._max_columns or total)
        space = self._grid.spacing()
        fit = (width + space) // max(1, self._item_width() + space)
        return max(1, min(limit, fit))

    def _reflow(self, width):
        """Reubica las tarjetas solo si cambio la cantidad de columnas."""
        columns = self._columns_for(width)
        if columns == self._columns:
            return
        self._columns = columns
        for widget in self._widgets:
            self._grid.removeWidget(widget)
        for index, widget in enumerate(self._widgets):
            self._grid.addWidget(widget, index // columns, index % columns)
        # Columnas de igual ancho; las que sobran de un acomodo anterior quedan sin peso
        for column in range(max(len(self._widgets), 1)):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        self.updateGeometry()

    def resizeEvent(self, event):
        """Recalcula columnas y alto cada vez que cambia el ancho."""
        self._reflow(event.size().width())
        height = self._height_for(event.size().width())
        if height != self._height:
            self._height = height
            self.updateGeometry()   # el padre vuelve a acomodar con el alto nuevo
        super().resizeEvent(event)

    def _height_for(self, width):
        """Alto necesario para el ancho dado, contando textos que bajan de línea (sin mover nada)."""
        if not self._widgets:
            return 0
        columns = self._columns_for(width)
        space = self._grid.spacing()
        column_width = max(1, int((width - space * (columns - 1)) / columns))
        total = 0
        for start in range(0, len(self._widgets), columns):
            row = self._widgets[start:start + columns]
            total += max(self._item_height(w, column_width) for w in row)
        return total + space * ((len(self._widgets) - 1) // columns)

    @staticmethod
    def _item_height(widget, width):
        """Alto de una tarjeta para un ancho dado (respeta textos con ajuste de línea)."""
        height = widget.heightForWidth(width) if widget.hasHeightForWidth() else -1
        return max(height, widget.minimumSizeHint().height(), widget.minimumHeight())

    def minimumSizeHint(self):
        """Permite angostarse hasta una sola columna; el alto es el del acomodo actual."""
        return QSize(self._item_width(), self._height_for(max(self.width(), self._item_width())))

    def sizeHint(self):
        """Tamaño ideal con el acomodo actual."""
        return QSize(self._grid.sizeHint().width(), self._height_for(max(self.width(), self._item_width())))


# --- Encabezado que baja sus botones cuando no caben ---

def fit_header(header, texts, actions):
    """Pone los botones debajo del título si la fila completa no cabe en el ancho del encabezado.

    header es el widget, texts y actions sus dos layouts; se llama desde su resizeEvent.
    """
    layout = header.layout()
    needed = texts.minimumSize().width() + actions.sizeHint().width() + layout.spacing()
    direction = (QBoxLayout.Direction.LeftToRight if header.width() >= needed
                 else QBoxLayout.Direction.TopToBottom)
    if layout.direction() != direction:
        layout.setDirection(direction)
        header.updateGeometry()


# --- Fila que se apila cuando la ventana es angosta ---

class AdaptiveRow(QWidget):
    """Fila de paneles que pasa a columna (uno debajo de otro) cuando el ancho no alcanza.

    breakpoint es el ancho mínimo, en medidas de diseño, para mostrarlos lado a lado;
    por debajo se apilan y la página se desliza en vertical.
    """

    def __init__(self, breakpoint, spacing=16, parent=None):
        """Crea la fila vacía con su ancho de corte y el espacio entre paneles."""
        super().__init__(parent)
        self._breakpoint = px(breakpoint)
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(px(spacing))
        self._stretches = []

    def add(self, widget, stretch=1):
        """Agrega un panel con su proporción de ancho cuando están lado a lado."""
        self._box.addWidget(widget, stretch)
        self._stretches.append(stretch)
        return widget

    def _widgets(self):
        """Devuelve los paneles en orden."""
        return [self._box.itemAt(i).widget() for i in range(self._box.count())]

    def resizeEvent(self, event):
        """Cambia entre fila y columna según el ancho disponible."""
        side_by_side = event.size().width() >= max(self._breakpoint, self._row_minimum())
        direction = QBoxLayout.Direction.LeftToRight if side_by_side else QBoxLayout.Direction.TopToBottom
        if self._box.direction() != direction:
            self._box.setDirection(direction)
            # En columna cada panel usa su alto natural; en fila vuelven sus proporciones
            for index, stretch in enumerate(self._stretches):
                self._box.setStretch(index, stretch if side_by_side else 0)
            self.updateGeometry()
        super().resizeEvent(event)

    def _row_minimum(self):
        """Ancho mínimo para mostrar todos los paneles lado a lado."""
        widgets = self._widgets()
        return sum(w.minimumSizeHint().width() for w in widgets) + self._box.spacing() * max(0, len(widgets) - 1)

    def minimumSizeHint(self):
        """Permite angostarse hasta el panel más ancho (modo columna)."""
        width = max((w.minimumSizeHint().width() for w in self._widgets()), default=0)
        return QSize(width, self._box.minimumSize().height())
