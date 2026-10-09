from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ...core.app_config import AppConfig

def _section(name):
    """Devuelve la sección indicada de theme.conf como diccionario de textos."""
    theme = AppConfig.get_instance().file("theme")
    return theme.section_text(name) if theme else {}


def detect_dark_mode():
    """Indica si se usa el modo oscuro según theme_mode de ui.conf; en 'auto' sigue el tema del sistema."""
    mode = str(AppConfig.get_instance().get("ui", "theme_mode", default="auto")).lower()
    if mode in ("dark", "dark"):
        return True
    if mode in ("light", "light"):
        return False

    # Esquema de color que informa Qt
    try:
        schema = QApplication.styleHints().colorScheme()
        if schema == Qt.ColorScheme.Dark:
            return True
        if schema == Qt.ColorScheme.Light:
            return False
    except Exception:
        pass

    # Respaldo: registro de Windows (AppsUseLightTheme = 0 significa modo oscuro)
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:
        return True


def get_colors(dark_mode):
    """Construye la paleta completa del modo indicado a partir de theme.conf.

    Las claves resultantes son las variables disponibles en los .css como var(--clave).
    """
    palette = dict(_section("DarkMode_colors" if dark_mode else "LightMode_colors"))

    # Colores de señales (signal_*) y sus fondos (signal_bg_*)
    signals = _section("Signal_colors" if dark_mode else "Signal_colors_light") or _section("Signal_colors")
    backgrounds = _section("Signal_backgrounds_dark" if dark_mode else "Signal_backgrounds_light")
    for name, value in signals.items():
        palette[f"signal_{name}"] = value
    for name, value in backgrounds.items():
        palette[f"signal_bg_{name}"] = value

    # Tipografía, semáforo (traffic_light_*) y superficie de video (video_*)
    palette.update(_section("Typography"))
    for name, value in _section("Traffic_light").items():
        palette[f"traffic_light_{name}"] = value
    for name, value in _section("Video_surface").items():
        palette[f"video_{name}"] = value

    palette["mode"] = "dark" if dark_mode else "light"
    return palette
