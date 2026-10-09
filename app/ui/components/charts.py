from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..scale import layout_factor, pt, px
from ..styles.theme import color

# Margenes del área de dibujo (izquierda, derecha, arriba, abajo) en pixeles
_M_LEFT, _M_RIGHT, _M_TOP, _M_BOTTOM = 44, 12, 14, 28


# --- Utilidades ---

def _blend(c1, c2, t):
    """Mezcla dos colores de forma lineal según t (0 = c1, 1 = c2)."""
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


def _nice_scale(max_value, divisions=4):
    """Devuelve el máximo redondeado del eje Y en pasos de 1, 2, 2.5 o 5 por 10^n."""
    if max_value <= 0:
        return 1.0
    raw = max_value / divisions
    power = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    for step in (1, 2, 2.5, 5, 10):
        if raw <= step * power:
            return step * power * divisions
    return max_value


# --- Base común ---

class _BaseChart(QWidget):
    """Base de las gráficas dibujadas con QPainter usando la paleta del tema.

    Muestra un tooltip al pasar el ratón y un mensaje si no hay datos. Los colores
    salen de theme.conf (accent, border, muted_text, área, etc.).
    """

    def __init__(self, min_height=220, parent=None):
        """Configura el seguimiento del ratón, el alto mínimo y el mensaje sin datos."""
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(px(min_height))
        self._k = layout_factor()   # las gráficas se dibujan en medidas de diseño y se escalan
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.empty_message = "Aún no hay datos para este periodo"
        self._hover = None

    def _w(self):
        """Ancho del widget en medidas de diseño (sin escala)."""
        return self.width() / self._k

    def _h(self):
        """Alto del widget en medidas de diseño (sin escala)."""
        return self.height() / self._k

    def _painter(self):
        """Crea el pintor con la escala de la pantalla aplicada."""
        painter = QPainter(self)
        painter.scale(self._k, self._k)
        return painter

    def _pos(self, event):
        """Posicion del ratón en medidas de diseño."""
        return event.position() / self._k

    def _source(self, painter, size=8.0, bold=False):
        """Asigna al pintor la fuente del widget con el tamaño (grupo small de ui.conf) y el grosor indicados."""
        source = QFont(self.font())
        source.setPointSizeF(pt(size, "small") / self._k)   # el pintor ya esta escalado
        source.setBold(bold)
        painter.setFont(source)

    def _empty(self, painter):
        """Dibuja el mensaje centrado de gráfica sin datos."""
        self._source(painter, 9.5)
        painter.setPen(color("muted_text"))
        painter.drawText(QRectF(0, 0, self._w(), self._h()), Qt.AlignmentFlag.AlignCenter, self.empty_message)

    def leaveEvent(self, event):
        """Quita el resaltado y oculta el tooltip al salir el ratón."""
        self._hover = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def _y_axis(self, painter, area, max_value, divisions=4):
        """Dibuja las líneas guia horizontales y las etiquetas del eje Y."""
        self._source(painter, 7.5)
        grid = color("border")
        for i in range(divisions + 1):
            y = area.bottom() - area.height() * i / divisions
            painter.setPen(QPen(grid, 1, Qt.PenStyle.SolidLine if i == 0 else Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            value = max_value * i / divisions
            text = f"{value:.0f}" if max_value >= divisions else f"{value:.1f}"
            painter.setPen(color("muted_text"))
            painter.drawText(QRectF(0, y - 8, _M_LEFT - 8, 16),
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)


# --- Gráfica de barras ---

class BarChart(_BaseChart):
    """Barras verticales por categoria (por ejemplo vehículos por hora).

    Los indices de `highlight` (horas pico) se pintan con el color de acento y llevan
    su valor encima.
    """

    def __init__(self, unit="veh", parent=None):
        """Crea la gráfica vacía con la unidad que se muestra en el tooltip."""
        super().__init__(parent=parent)
        self.unit = unit
        self.labels, self.values, self.highlight = [], [], set()
        self.label_every = 1

    def set_data(self, labels, values, highlight=(), label_every=1):
        """Carga etiquetas, valores y barras destacadas; muestra una etiqueta cada label_every."""
        self.labels, self.values = list(labels), [float(v) for v in values]
        self.highlight = set(highlight)
        self.label_every = max(1, label_every)
        self.update()

    def _bars(self):
        """Devuelve el área de dibujo, el paso entre barras y el ancho de cada barra."""
        area = QRectF(_M_LEFT, _M_TOP, self._w() - _M_LEFT - _M_RIGHT, self._h() - _M_TOP - _M_BOTTOM)
        n = max(1, len(self.values))
        step = area.width() / n
        width = max(2.0, step - 2)  # 2 px de separación entre barras
        return area, step, width

    def paintEvent(self, event):
        """Dibuja el eje, las barras y las etiquetas del eje X."""
        del event
        p = self._painter()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values or max(self.values) <= 0:
            self._empty(p)
            return
        area, step, width = self._bars()
        max_value = _nice_scale(max(self.values))
        self._y_axis(p, area, max_value)

        # Barras: acento en las destacadas, acento translucido en el resto
        base = color("accent")
        smooth = QColor(base)
        smooth.setAlpha(110)
        for i, value in enumerate(self.values):
            height = area.height() * value / max_value
            x = area.left() + i * step + (step - width) / 2
            rect = QRectF(x, area.bottom() - height, width, height)
            fill = base if i in self.highlight else smooth
            if self._hover == i:
                fill = color("accent_hover")
            path = QPainterPath()
            radius = min(4.0, width / 2, height)
            path.addRoundedRect(rect.adjusted(0, 0, 0, radius), radius, radius)  # solo redondeo arriba
            p.save()
            p.setClipRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height()))
            p.fillPath(path, fill)
            p.restore()

            if i in self.highlight and value > 0:  # etiqueta directa solo en las destacadas
                self._source(p, 7.5, True)
                p.setPen(color("text"))
                p.drawText(QRectF(x - 20, rect.top() - 16, width + 40, 14),
                           Qt.AlignmentFlag.AlignCenter, f"{value:.0f}")

        # Etiquetas del eje X
        self._source(p, 7.5)
        p.setPen(color("muted_text"))
        for i, label in enumerate(self.labels):
            if i % self.label_every:
                continue
            x = area.left() + i * step
            p.drawText(QRectF(x - 10, area.bottom() + 6, step + 20, 16), Qt.AlignmentFlag.AlignCenter, label)

    def mouseMoveEvent(self, event):
        """Resalta la barra bajo el ratón y muestra su valor en un tooltip."""
        if not self.values:
            return
        area, step, _ = self._bars()
        i = int((self._pos(event).x() - area.left()) // step)
        if 0 <= i < len(self.values):
            if i != self._hover:
                self._hover = i
                self.update()
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{self.labels[i]}\n{self.values[i]:.1f} {self.unit}", self)


# --- Gráfica de línea ---

class LineChart(_BaseChart):
    """Tendencia en el tiempo: línea con área degradada, cruceta y tooltip."""

    def __init__(self, unit="veh", parent=None):
        """Crea la gráfica vacía con la unidad que se muestra en el tooltip."""
        super().__init__(parent=parent)
        self.unit = unit
        self.labels, self.values = [], []
        self.label_every = 1

    def set_data(self, labels, values, label_every=1):
        """Carga etiquetas y valores; muestra una etiqueta cada label_every."""
        self.labels, self.values = list(labels), [float(v) for v in values]
        self.label_every = max(1, label_every)
        self.update()

    def _points(self, area, max_value):
        """Convierte los valores en puntos del área y devuelve también el paso horizontal."""
        n = len(self.values)
        step = area.width() / max(1, n - 1)
        return [QPointF(area.left() + i * step, area.bottom() - area.height() * v / max_value)
                for i, v in enumerate(self.values)], step

    def paintEvent(self, event):
        """Dibuja el eje, el área degradada, la línea, las etiquetas y la cruceta."""
        del event
        p = self._painter()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.values) < 2 or max(self.values) <= 0:
            self._empty(p)
            return
        area = QRectF(_M_LEFT, _M_TOP, self._w() - _M_LEFT - _M_RIGHT, self._h() - _M_TOP - _M_BOTTOM)
        max_value = _nice_scale(max(self.values))
        self._y_axis(p, area, max_value)
        points, step = self._points(area, max_value)

        # Trazo de la línea y área cerrada hasta la base
        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)
        fill = QPainterPath(line)
        fill.lineTo(points[-1].x(), area.bottom())
        fill.lineTo(points[0].x(), area.bottom())
        fill.closeSubpath()

        # Relleno degradado de arriba hacia abajo y línea de acento
        accent = color("accent")
        gradient = QLinearGradient(0, area.top(), 0, area.bottom())
        top, below = QColor(accent), QColor(accent)
        top.setAlpha(90)
        below.setAlpha(5)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, below)
        p.fillPath(fill, gradient)
        p.setPen(QPen(accent, 2))
        p.drawPath(line)

        # Etiquetas del eje X
        self._source(p, 7.5)
        p.setPen(color("muted_text"))
        for i, label in enumerate(self.labels):
            if i % self.label_every:
                continue
            x = max(0.0, min(self._w() - 64.0, points[i].x() - 32))  # evita que se corte en los bordes
            p.drawText(QRectF(x, area.bottom() + 6, 64, 16), Qt.AlignmentFlag.AlignCenter, label)

        # Cruceta y punto sobre el valor bajo el ratón
        if self._hover is not None and self._hover < len(points):
            point = points[self._hover]
            p.setPen(QPen(color("border_strong"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(point.x(), area.top()), QPointF(point.x(), area.bottom()))
            p.setPen(QPen(color("area"), 2))
            p.setBrush(accent)
            p.drawEllipse(point, 5, 5)

    def mouseMoveEvent(self, event):
        """Marca el punto más cercano al ratón y muestra su valor en un tooltip."""
        if len(self.values) < 2:
            return
        area = QRectF(_M_LEFT, _M_TOP, self._w() - _M_LEFT - _M_RIGHT, self._h() - _M_TOP - _M_BOTTOM)
        step = area.width() / (len(self.values) - 1)
        i = int(round((self._pos(event).x() - area.left()) / step))
        i = max(0, min(len(self.values) - 1, i))
        if i != self._hover:
            self._hover = i
            self.update()
        QToolTip.showText(event.globalPosition().toPoint(),
                          f"{self.labels[i]}\n{self.values[i]:.0f} {self.unit}", self)


# --- Mapa de calor ---

class HeatmapChart(_BaseChart):
    """Matriz filas por columnas (día de la semana por hora) con escala de un solo tono."""

    def __init__(self, rows, columns, unit="veh/h", parent=None):
        """Crea el mapa con los nombres de filas y columnas y la unidad del tooltip."""
        super().__init__(min_height=230, parent=parent)
        self.rows, self.columns, self.unit = list(rows), list(columns), unit
        self.matrix = []
        self.every_column = 3

    def set_data(self, matrix):
        """Carga la matriz de valores (una lista por fila) y repinta."""
        self.matrix = matrix
        self.update()

    def _geometry(self):
        """Devuelve el margen izquierdo, el margen superior y el tamaño de cada celda."""
        left, top, below = 42, 6, 40
        cell_width = (self._w() - left - 8) / max(1, len(self.columns))
        cell_height = (self._h() - top - below) / max(1, len(self.rows))
        return left, top, cell_width, cell_height

    def paintEvent(self, event):
        """Dibuja las celdas, los nombres de filas y columnas y la leyenda."""
        del event
        p = self._painter()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        max_value = max((max(row) for row in self.matrix), default=0)
        if max_value <= 0:
            self._empty(p)
            return
        left, top, width, height = self._geometry()
        low, high_color = color("alternative_area"), color("accent")

        # Celdas: el exponente 0.8 realza los valores bajos para que se distingan
        for f, row in enumerate(self.matrix):
            for c, value in enumerate(row):
                rect = QRectF(left + c * width + 1, top + f * height + 1, width - 2, height - 2)
                fill = _blend(low, high_color, (value / max_value) ** 0.8)
                p.setPen(QPen(color("text"), 1.5) if self._hover == (f, c) else Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawRoundedRect(rect, 3, 3)

        # Nombres de filas y de una de cada every_column columnas
        self._source(p, 7.5)
        p.setPen(color("muted_text"))
        for f, name in enumerate(self.rows):
            p.drawText(QRectF(0, top + f * height, left - 6, height),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)
        base = top + len(self.rows) * height
        for c, name in enumerate(self.columns):
            if c % self.every_column == 0:
                p.drawText(QRectF(left + c * width - 10, base + 3, width + 20, 14),
                           Qt.AlignmentFlag.AlignCenter, name)

        # Leyenda de menos a más
        legend = QRectF(self._w() - 170, base + 22, 110, 8)
        gradient = QLinearGradient(legend.topLeft(), legend.topRight())
        gradient.setColorAt(0, low)
        gradient.setColorAt(1, high_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(legend, 3, 3)
        p.setPen(color("muted_text"))
        p.drawText(QRectF(legend.left() - 50, legend.top() - 4, 46, 16),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Menos")
        p.drawText(QRectF(legend.right() + 4, legend.top() - 4, 50, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Más")

    def mouseMoveEvent(self, event):
        """Resalta la celda bajo el ratón y muestra su valor en un tooltip."""
        if not self.matrix:
            return
        left, top, width, height = self._geometry()
        c = int((self._pos(event).x() - left) // width)
        f = int((self._pos(event).y() - top) // height)
        if 0 <= f < len(self.matrix) and 0 <= c < len(self.matrix[f]):
            if (f, c) != self._hover:
                self._hover = (f, c)
                self.update()
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{self.rows[f]} {self.columns[c]}\n{self.matrix[f][c]:.1f} {self.unit}", self)
