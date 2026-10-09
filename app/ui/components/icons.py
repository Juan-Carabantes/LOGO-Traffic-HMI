import weakref

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from ...core.settings import ICONS_DIR
from ..styles.theme import current_palette
from ..scale import tx

# Cache de iconos generados y widgets registrados para refrescarse al recargar el tema (F5)
_cache = {}
_registered = []


# --- Generación de iconos ---

def _color(color):
    """Convierte una clave de la paleta ('accent') o un hex ('#ffffff') en un hex."""
    if not color:
        return None
    if str(color).startswith("#"):
        return str(color)
    return str(current_palette().get(color, "#8b97a8"))


def _pixmap(name, color, size, scale=2.0):
    """Renderiza el SVG indicado con el color pedido y devuelve un QPixmap nitido.

    Los SVG usan stroke="currentColor"; Qt no entiende currentColor, así que se
    reemplaza por el color pedido antes de renderizar.
    """
    path = ICONS_DIR / f"{name}.svg"
    if not path.exists():
        return QPixmap()
    svg = path.read_text(encoding="utf-8")
    hex_color = _color(color)
    if hex_color:
        svg = svg.replace("currentColor", hex_color)

    # Se dibuja al doble de tamaño (ya escalado a la pantalla) y se ajusta la densidad
    side = int(tx(size) * scale)
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, side, side))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def icon(name, color="soft_text", size=20):
    """Devuelve el QIcon del SVG con el color indicado, usando la cache."""
    key = (name, _color(color), size)
    if key not in _cache:
        _cache[key] = QIcon(_pixmap(name, color, size))
    return _cache[key]


def state_icon(name, normal="soft_text", active="accent", size=20, disabled="border_strong"):
    """Crea un icono con color distinto cuando el botón esta seleccionado (checked) o deshabilitado."""
    ic = QIcon()
    ic.addPixmap(_pixmap(name, normal, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(_pixmap(name, active, size), QIcon.Mode.Normal, QIcon.State.On)
    ic.addPixmap(_pixmap(name, active, size), QIcon.Mode.Active, QIcon.State.On)
    ic.addPixmap(_pixmap(name, disabled, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


def icon_pixmap(name, color="soft_text", size=20):
    """Devuelve el icono como QPixmap, para usarlo en un QLabel."""
    return _pixmap(name, color, size)


# --- Registro y refresco al cambiar el tema ---

def apply(button, name, color="soft_text", size=18):
    """Asigna un icono a un botón y lo registra para refrescarlo al cambiar el tema."""
    def refresh(b=weakref.ref(button)):
        """Vuelve a asignar el icono si el botón sigue existiendo."""
        widget = b()
        if widget is not None:
            widget.setIcon(icon(name, color, size))
            widget.setIconSize(QSize(tx(size), tx(size)))
    refresh()
    record(button, refresh, label="icon")
    return button


def record(widget, callback, label=None):
    """Guarda el callback que refresca el widget al recargar el tema.

    Con etiqueta, un nuevo registro reemplaza al anterior del mismo widget.
    """
    if label is not None:
        _registered[:] = [
            r for r in _registered if not (r[0]() is widget and r[2] == label)
        ]
    _registered.append((weakref.ref(widget), callback, label))


def refresh_all():
    """Vuelve a generar todos los iconos registrados después de recargar el tema."""
    _cache.clear()
    live = []
    for ref, callback, label in _registered:
        if ref() is not None:
            try:
                callback()
                live.append((ref, callback, label))
            except RuntimeError:
                pass  # widget ya destruido por Qt
    _registered[:] = live
