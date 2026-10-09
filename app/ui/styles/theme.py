import logging
import re

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from ...core.app_config import AppConfig
from ...core.settings import STYLES_DIR
from ..scale import scale_css

_log = logging.getLogger(__name__)
# Coincide con comentarios /* ... */ (se dejan intactos) o con var(--clave)
_RE_VAR = re.compile(r"/\*[\s\S]*?\*/|var\(\s*--([A-Za-z0-9_\-]+)\s*\)")

_current_palette = {}


# --- Construcción de la hoja de estilos ---

# Las hojas .css viven en esta carpeta, organizadas por bloque: base/ (estilos globales,
# tipografía y variantes de botones), components/, layout/ (barras superior y lateral),
# widgets/, views/ (una hoja por vista) y dialogs/. En ellas se usa var(--clave), donde
# <clave> es cualquier color o valor definido en app/config/theme.conf.

def _css_files():
    """Lee el orden de carga de ui.conf ([styles] files); si no existe, carga todos los .css."""
    cfg = AppConfig.get_instance()
    text = cfg.get_text("ui", "files", default="")
    files = [line.strip() for line in text.replace(",", "\n").splitlines() if line.strip()]
    if files:
        return [STYLES_DIR / a for a in files]
    return sorted(STYLES_DIR.rglob("*.css"))


def _replace_vars(css, palette, file):
    """Sustituye cada var(--clave) del CSS por su valor en la paleta."""
    def replacement(match):
        """Devuelve el valor de la variable, o el texto original si es un comentario o no existe."""
        key = match.group(1)
        if key is None:  # es un comentario
            return match.group(0)
        if key in palette:
            return str(palette[key])
        _log.warning("Variable var(--%s) no definida en theme.conf (%s)", key, file.name)
        return match.group(0)

    return _RE_VAR.sub(replacement, css)


def build_stylesheet(palette):
    """Une todas las hojas .css en orden y sustituye las variables de la paleta."""
    blocks = []
    for file in _css_files():
        if not file.exists():
            _log.warning("Hoja de estilo no encontrada: %s", file)
            continue
        css = file.read_text(encoding="utf-8")
        relative = file.relative_to(STYLES_DIR).as_posix() if file.is_relative_to(STYLES_DIR) else file.name
        blocks.append(f"/* ===== {relative} ===== */\n{scale_css(_replace_vars(css, palette, file))}")
    return "\n\n".join(blocks)


def apply_theme(app, palette):
    """Aplica la hoja completa a nivel de QApplication (cubre ventanas y dialogos)."""
    global _current_palette
    _current_palette = dict(palette)
    app.setStyleSheet(build_stylesheet(palette))
    # Color de los enlaces (el CSS de Qt no lo controla en textos enriquecidos)
    qt_palette = app.palette()
    qt_palette.setColor(QPalette.ColorRole.Link, QColor(str(palette.get("accent", "#2563eb"))))
    app.setPalette(qt_palette)
    for widget in app.allWidgets():
        widget.update()


def reload_theme(dark_mode=None):
    """Relee theme.conf, ui.conf y los .css y los aplica sin reiniciar la app."""
    from ..components import icons
    from .palette import detect_dark_mode, get_colors

    cfg = AppConfig.get_instance()
    cfg.file("theme").reload()
    cfg.file("ui").reload()
    if dark_mode is None:
        dark_mode = detect_dark_mode()
    palette = get_colors(dark_mode)
    app = QApplication.instance()
    if app is not None:
        apply_theme(app, palette)
    icons.refresh_all()
    return palette


# --- Acceso a la paleta desde widgets pintados a mano (QPainter) ---

def color(key, fallback="#888888"):
    """Devuelve un QColor de la paleta activa (por ejemplo color('traffic_light_red_on'))."""
    return QColor(str(_current_palette.get(key, fallback)))


def current_palette():
    """Devuelve una copia de la paleta activa."""
    return dict(_current_palette)


# --- Utilidades para asignar selectores desde el código ---

# Para dar estilo desde el código no se usa setStyleSheet(); se asignan selectores:
#   widget.setObjectName("statCard")          ->  QFrame#statCard { ... }
#   button.setProperty("variant", "primary")  ->  QPushButton[variant="primary"] { ... }
#   set_prop(chip, "state", "success")        ->  QFrame#statusChip[state="success"] { ... } (cambios en vivo)

def refresh_style(widget, recursive=True):
    """Fuerza a Qt a reevaluar los selectores tras cambiar una propiedad."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    if recursive:
        for child in widget.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
    widget.update()


def set_prop(widget, name, value, recursive=True):
    """Cambia una propiedad dinamica y refresca el estilo si el valor cambio."""
    if widget.property(name) == value:
        return widget
    widget.setProperty(name, value)
    refresh_style(widget, recursive)
    return widget
