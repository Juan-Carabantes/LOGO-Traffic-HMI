from .app_config import APP_DIR, CONFIG_DIR, PROJECT_DIR, AppConfig

# Rutas definidas en app.conf -> [paths]; los datos de ejecución quedan en la raiz del proyecto
_cfg = AppConfig.get_instance()

# --- Recursos del código ---

ICON_PATH = _cfg.path("app", "app_icon") or APP_DIR / "assets" / "icons" / "logo_traffic_hmi.png"
ICONS_DIR = _cfg.path("app", "icons_dir") or APP_DIR / "assets" / "icons"
STYLES_DIR = _cfg.path("app", "styles_dir") or APP_DIR / "ui" / "styles"

# --- Datos generados en ejecución ---

DATA_DIR = _cfg.path("app", "data_dir") or PROJECT_DIR / "data"
LOGS_DIR = _cfg.path("app", "logs_dir") or PROJECT_DIR / "logs"
DATABASE_PATH = _cfg.path("app", "database") or DATA_DIR / "logo_traffic_hmi.sqlite3"
RECORDINGS_DIR = _cfg.path("camera", "recordings_dir") or PROJECT_DIR / "recordings"
MODELS_DIR = _cfg.path("app", "models_dir") or PROJECT_DIR / "models"

__all__ = [
    "APP_DIR", "PROJECT_DIR", "CONFIG_DIR", "ICON_PATH", "ICONS_DIR", "STYLES_DIR",
    "DATA_DIR", "LOGS_DIR", "DATABASE_PATH", "RECORDINGS_DIR",
]
