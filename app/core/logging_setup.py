import logging
import sys
from datetime import datetime

from .app_config import AppConfig
from .settings import LOGS_DIR

FILE_FORMAT = "[%(asctime)s.%(msecs)03d] %(levelname)-7s %(name)s: %(message)s"
CONSOLE_FORMAT = "[%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_session_file = None


def configure_logging(level=logging.INFO):
    """Configura el registro en consola y en el archivo de sesión; devuelve la ruta del archivo.

    Cada ejecución genera logs/session_AAAA-MM-DD_HH-MM-SS.txt con todo lo que pasa en
    la app. Los módulos solo usan logging.getLogger(__name__).
    """
    global _session_file
    cfg = AppConfig.get_instance()
    prefix = cfg.get_text("app", "session_prefix", "session")
    max_value = int(cfg.get("app", "max_session_files", default=0) or 0)

    # Archivo nuevo de sesión, borrando los antiguos si hay límite
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _delete_old(prefix, max_value)
    _session_file = LOGS_DIR / datetime.now().strftime(f"{prefix}_%Y-%m-%d_%H-%M-%S.txt")

    # Reemplaza los manejadores previos por archivo y consola
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file = logging.FileHandler(_session_file, encoding="utf-8")
    file.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    root.addHandler(file)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    root.addHandler(console)

    # Reduce el detalle de librerias muy verbosas
    for noisy in ("ultralytics", "PIL", "matplotlib", "snap7"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("app").info("=== INICIO DE %s ===", cfg.get_text("app", "name", "LOGO! Traffic HMI"))
    return _session_file


def _delete_old(prefix, max_value):
    """Conserva los últimos (max_value - 1) archivos de sesión; 0 = sin límite."""
    if max_value <= 0:
        return
    existing = sorted(LOGS_DIR.glob(f"{prefix}_*.txt"))
    for old in existing[: max(0, len(existing) - (max_value - 1))]:
        try:
            old.unlink()
        except OSError:
            pass


def install_exception_hook(callback=None):
    """Registra en el log cualquier excepción no controlada y avisa a la interfaz."""

    def hook(kind, value, trace):
        """Guarda la excepción en el log y llama al callback; Ctrl+C sigue el flujo normal."""
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, trace)
            return
        logging.getLogger("app").critical("Excepcion no controlada", exc_info=(kind, value, trace))
        if callback:
            try:
                callback(f"{kind.__name__}: {value}")
            except Exception:
                pass

    sys.excepthook = hook
