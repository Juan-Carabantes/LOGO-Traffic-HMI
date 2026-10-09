# Nucleo de la aplicación (sin interfaz gráfica).
#   app_config         Acceso unificado a app/config/*.conf
#   conf_file          Lectura y escritura de .conf conservando comentarios
#   settings           Rutas del proyecto
#   io_map             Entradas y salidas del Logo (app/config/io.conf)
#   timers_map         Bloques de temporizador (app/config/timers.conf)
#   hardware_detector  Perfil de rendimiento según CPU/GPU
#   logging_setup      Registro de sesión y excepciones
#   formatting         Formatos de tiempo y color

from .app_config import CONFIG_DIR, PROJECT_DIR, AppConfig

__all__ = ["AppConfig", "CONFIG_DIR", "PROJECT_DIR"]
