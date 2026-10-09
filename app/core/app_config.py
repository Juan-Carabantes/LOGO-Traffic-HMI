import logging
import os
import shutil
import sys
import threading
from pathlib import Path

from .conf_file import ConfFile

# --- Rutas ---

# En desarrollo todo vive en la carpeta del proyecto. En el .exe (PyInstaller) los recursos
# de solo lectura (código, iconos, estilos, valores de fabrica y modelos) van dentro del
# ejecutable y los datos del usuario (configuración, historial, registros y grabaciones)
# en Documentos\LOGO Traffic HMI, para que se conserven entre versiones.
FROZEN = bool(getattr(sys, "frozen", False))


def _documents_dir():
    """Devuelve la carpeta Documentos del usuario (respeta la redirección a OneDrive en Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:   # 5 = Documentos
                return Path(buffer.value)
        except Exception:
            pass
    return Path.home() / "Documents"


if FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    PROJECT_DIR = _documents_dir() / "LOGO Traffic HMI"
    CONFIG_DIR = PROJECT_DIR / "config"
else:
    RESOURCE_DIR = Path(__file__).resolve().parents[2]
    PROJECT_DIR = RESOURCE_DIR
    CONFIG_DIR = RESOURCE_DIR / "app" / "config"

APP_DIR = RESOURCE_DIR / "app"
DEFAULTS_DIR = APP_DIR / "config" / "defaults"
BUNDLED_MODELS_DIR = RESOURCE_DIR / "models"   # modelos incluidos en el .exe (solo lectura)
MASTER_FILE = CONFIG_DIR / "app.conf"


def _prepare_user_config():
    """En el .exe copia la configuración inicial a Documentos sin reemplazar la que ya exista."""
    if not FROZEN:
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for source in (APP_DIR / "config").glob("*.conf"):
        target = CONFIG_DIR / source.name
        if not target.exists():
            shutil.copy2(source, target)


_prepare_user_config()

_log = logging.getLogger(__name__)


class AppConfig:
    """Fachada única sobre todos los archivos .conf del proyecto.

    app/config/app.conf es el archivo maestro; su sección [modules] enlaza un .conf
    por área (plc, timers, camera, vision, analytics, ui, theme, io). La carpeta
    app/config/defaults/ guarda los mismos archivos con los valores de fabrica, que
    usa el botón "Restablecer" de cada área.

    Uso desde el código:
        cfg = AppConfig.get_instance()
        cfg.get("plc", "ip")                       # busca la clave en cualquier sección
        cfg.get("timers", "B3", "seconds")         # sección + clave
        cfg.get("timers")                          # dict {sección: {clave: valor}}
        cfg.get_text("plc", "tsap_local")          # valor como texto, sin convertir
        cfg.section("io", "Q1")                    # dict de una sección
        cfg.set("plc", "ip", "192.168.0.10")       # escribe solo esa línea del .conf
        cfg.default("plc", "ip")                   # valor de fabrica (app/config/defaults/)
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Devuelve la instancia única, creandola la primera vez de forma segura entre hilos."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = AppConfig()
        return cls._instance

    def __init__(self):
        """Carga el archivo maestro, sus módulos enlazados y crea las carpetas de datos."""
        self._hardware_info = None
        self._factory = {}
        self.master = ConfFile(MASTER_FILE)
        self.modules = {}
        self._load_modules()
        self._create_dirs()

    # --- Carga ---

    def _load_modules(self):
        """Abre cada .conf listado en la sección [modules] de app.conf."""
        self.modules = {"app": self.master}
        for name, file in self.master.section_text("modules").items():
            path = CONFIG_DIR / file
            if not path.exists():
                _log.warning("Archivo de configuración no encontrado: %s", path)
            self.modules[name] = ConfFile(path)

    def _create_dirs(self):
        """Crea las carpetas de datos, registros y grabaciones si no existen."""
        for key in ("data_dir", "logs_dir"):
            path = self.path("app", key)
            if path:
                path.mkdir(parents=True, exist_ok=True)
        recordings = self.path("camera", "recordings_dir")
        if recordings:
            recordings.mkdir(parents=True, exist_ok=True)

    def reload(self):
        """Vuelve a leer todos los .conf desde disco (útil tras editarlos a mano)."""
        self.master.reload()
        self._load_modules()

    def file(self, module):
        """Devuelve el ConfFile de un módulo, o None si no existe."""
        return self.modules.get(module)

    # --- Lectura ---

    def get(self, *keys, default=None):
        """Lee un valor convertido: (módulo), (módulo, clave|sección) o (módulo, sección, clave)."""
        if not keys:
            return default
        conf = self.modules.get(keys[0])
        if conf is None:
            return default

        # Solo el módulo: devuelve el archivo completo
        if len(keys) == 1:
            return conf.as_dict()

        # Módulo y nombre: primero se busca como sección y luego como clave
        if len(keys) == 2:
            name = keys[1]
            if conf.has_section(name):
                return conf.section(name)
            section = conf.find_section(name)
            if section is None:
                return default
            value = conf.get(section, name, default)
            return self._resolve_special(keys[0], name, value)

        section, key = keys[1], keys[2]
        value = conf.get(section, key, default)
        return self._resolve_special(keys[0], key, value)

    def get_text(self, module, key, default=""):
        """Lee un valor siempre como texto (sin convertir a número)."""
        conf = self.modules.get(module)
        if conf is None:
            return default
        section = conf.find_section(key)
        if section is None:
            return default
        return conf.get_text(section, key, default)

    def default(self, module, *keys, default=None, text=False):
        """Devuelve el valor de fabrica: default(módulo, clave) o default(módulo, sección, clave).

        Con text=True lo devuelve tal cual esta escrito, sin convertir a número.
        """
        # El archivo de fabrica se abre una sola vez y se guarda en cache
        conf = self._factory.get(module)
        if conf is None:
            file = "app.conf" if module == "app" else self.master.section_text("modules").get(module)
            path = DEFAULTS_DIR / str(file)
            if not file or not path.exists():
                return default
            conf = self._factory[module] = ConfFile(path)
        read_frame = conf.get_text if text else conf.get
        if len(keys) == 1:
            section = conf.find_section(keys[0])
            return default if section is None else read_frame(section, keys[0], default)
        return read_frame(keys[0], keys[1], default)

    def section(self, module, section):
        """Devuelve un dict {clave: valor} de una sección del módulo."""
        conf = self.modules.get(module)
        return conf.section(section) if conf else {}

    def sections(self, module):
        """Devuelve la lista de secciones del módulo."""
        conf = self.modules.get(module)
        return conf.sections() if conf else []

    def path(self, module, key, default=None):
        """Lee una ruta; si es relativa, las que empiezan con app/ son recursos y el resto datos del usuario."""
        value = self.get_text(module, key, default or "")
        if not value:
            return None
        path = Path(value)
        if path.is_absolute():
            return path
        return (RESOURCE_DIR if path.parts and path.parts[0] == "app" else PROJECT_DIR) / path

    def _resolve_special(self, module, key, value):
        """Traduce valores especiales, como profile = auto de vision al perfil sugerido por el hardware."""
        if module == "vision" and key == "profile" and str(value).lower() == "auto":
            return self.hardware_info.get("suggested_profile", "medium")
        return value

    @property
    def hardware_info(self):
        """Devuelve la información de CPU/GPU, detectandola solo la primera vez."""
        if self._hardware_info is None:
            from .hardware_detector import inspect_system_hardware
            self._hardware_info = inspect_system_hardware()
        return self._hardware_info

    # --- Escritura ---

    def set(self, *keys_and_value):
        """Escribe un valor: set(módulo, clave, valor) o set(módulo, sección, clave, valor).

        Con solo la clave se usa la sección que ya la contiene o, si no existe, la primera.
        """
        if len(keys_and_value) < 3:
            return
        module, *keys, value = keys_and_value
        conf = self.modules.get(module)
        if conf is None:
            _log.warning("Modulo de configuración desconocido: %s", module)
            return

        if len(keys) == 1:
            key = keys[0]
            section = conf.find_section(key) or (conf.sections() or ["general"])[0]
        else:
            section, key = keys[0], keys[1]
        try:
            conf.set(section, key, value)
        except OSError as error:
            _log.error("No se pudo guardar %s.%s: %s", module, key, error)

    def remove_section(self, module, section):
        """Borra una sección completa del .conf del módulo."""
        conf = self.modules.get(module)
        if conf is not None:
            conf.remove_section(section)

    def save(self):
        """Se conserva por compatibilidad: cada set() ya escribe en disco inmediatamente."""
        return None
