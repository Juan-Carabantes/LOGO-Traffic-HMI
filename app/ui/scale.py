import logging
import re

from PyQt6.QtGui import QCursor, QGuiApplication

from ..core.app_config import AppConfig

_log = logging.getLogger(__name__)

# --- Escala de la interfaz según la pantalla ---

# El diseño de referencia es una pantalla de 1920x1080 con la barra de tareas de Windows
# (área útil de unos 1920x1040 px logicos). En pantallas más pequeñas o más grandes todo
# se escala en proporción. Se usan dos factores:
#   layout: margenes, espacios, radios y medidas que no contienen texto
#   text:   letras, iconos y medidas que dependen del texto (altos de filas, anchos de menus)
# El texto se reduce menos que el resto para que siga siendo legible en pantallas pequeñas.
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1040
MIN_SCALE = 0.60
MAX_SCALE = 1.80

_layout = 1.0
_text = 1.0

# Tipos de letra configurables (ui.conf [fonts]) con su tamaño de fabrica en pt
FONT_DEFAULTS = {
    "text": 10.0, "page_title": 17.0, "card_title": 11.0, "subtitle": 8.5,
    "small": 8.5, "value": 22.0, "log": 9.0,
}

# Tamaños en px/pt dentro del CSS (el signo menos queda fuera para no tocar margenes negativos)
_RE_SIZE = re.compile(r"(?<![\w.#-])(\d+(?:\.\d+)?)(px|pt)\b")
_RE_FONT = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)(px|pt)", re.IGNORECASE)
# size(grupo, 9pt): tamaño de fabrica de un elemento que sigue al grupo de letra indicado
_RE_GROUP = re.compile(r"size\(\s*([a-z_]+)\s*,\s*(\d+(?:\.\d+)?)pt\s*\)")


def _auto_scale(screen):
    """Calcula el factor de la pantalla comparando su área útil con la de referencia."""
    if screen is None:
        return 1.0
    area = screen.availableGeometry()
    factor = min(area.width() / REFERENCE_WIDTH, area.height() / REFERENCE_HEIGHT)
    return max(MIN_SCALE, min(MAX_SCALE, factor))


def text_factor(layout):
    """Devuelve el factor del texto: baja más despacio que el layout en pantallas pequeñas."""
    return layout ** 0.6 if layout < 1.0 else layout


def target_screen():
    """Devuelve la pantalla donde esta el cursor (donde se abrira la ventana) o la principal."""
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


def init(screen=None):
    """Calcula los factores de escala al iniciar; ui.conf [window] scale permite fijarlo a mano."""
    global _layout, _text
    cfg = AppConfig.get_instance()
    value = cfg.get_text("ui", "scale", "auto").strip().lower().rstrip("%")
    automatic = _auto_scale(screen or target_screen())
    try:
        # Un valor manual se da en porcentaje respecto a la pantalla de referencia (100 = 1920x1080)
        chosen = automatic if value in ("", "auto") else float(value) / 100.0
    except ValueError:
        chosen = automatic
    _layout = max(MIN_SCALE, min(MAX_SCALE, chosen))
    _text = text_factor(_layout)
    _log.info("Escala de la interfaz: %.0f %% (texto %.0f %%)", _layout * 100, _text * 100)
    return _layout


def layout_factor():
    """Devuelve el factor actual para medidas sin texto."""
    return _layout


def font_factor():
    """Devuelve el factor actual para letras e iconos."""
    return _text


# --- Conversion de medidas ---

def px(value):
    """Escala una medida de layout (margenes, espacios, bordes) a la pantalla actual."""
    if not value:
        return 0
    return max(1, round(value * _layout))


def tx(value):
    """Escala una medida ligada al texto (iconos, altos de fila, anchos de menú)."""
    if not value:
        return 0
    return max(1, round(value * _text))


def pt(value, group=None):
    """Escala un tamaño de letra en puntos; con grupo aplica también el ajuste de ui.conf [fonts]."""
    return round(value * _text * (font_ratio(group) if group else 1.0), 2)


def font_ratio(group):
    """Devuelve la relación entre el tamaño configurado del grupo y su tamaño de fabrica."""
    default = FONT_DEFAULTS.get(group)
    if not default:
        return 1.0
    try:
        value = float(AppConfig.get_instance().get("ui", "fonts", group, default=default))
    except (TypeError, ValueError):
        return 1.0
    return max(0.5, min(3.0, value / default))


def scale_css(css):
    """Escala los tamaños del CSS: letras con el factor de texto (y su grupo) y el resto con el de layout."""
    fonts = []

    def keep_font(match):
        """Escala el tamaño de letra y lo protege para que no se vuelva a escalar."""
        value = float(match.group(2)) * _text
        fonts.append(f"{value:.2f}".rstrip("0").rstrip(".") + match.group(3))
        return f"{match.group(1)}\x00{len(fonts) - 1}\x00"

    def size(match):
        """Escala una medida de layout; los bordes de 1 px nunca bajan de 1."""
        value = float(match.group(1))
        if value == 0:
            return match.group(0)
        scaled = max(1.0, value * _layout) if match.group(2) == "px" else value * _layout
        if match.group(2) == "px":
            return f"{round(scaled)}px"
        return f"{scaled:.2f}".rstrip("0").rstrip(".") + "pt"

    def group_size(match):
        """Convierte size(grupo, Npt) en un tamaño final protegido."""
        value = float(match.group(2)) * _text * font_ratio(match.group(1))
        fonts.append(f"{value:.2f}".rstrip("0").rstrip(".") + "pt")
        return f"\x00{len(fonts) - 1}\x00"

    css = _RE_GROUP.sub(group_size, css)
    css = _RE_FONT.sub(keep_font, css)
    css = _RE_SIZE.sub(size, css)
    return re.sub(r"\x00(\d+)\x00", lambda m: fonts[int(m.group(1))], css)
