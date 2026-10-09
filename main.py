import os
import sys

# Reduce los mensajes internos de OpenCV al probar cámaras (debe ir antes de importar cv2)
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.core.logging_setup import configure_logging, install_exception_hook
from app.core.settings import ICON_PATH, LOGS_DIR


def main():
    """Inicia la aplicación: registro, tema, ventana principal y ciclo de eventos de Qt."""
    configure_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("LOGO! Traffic HMI")
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    def notify_error(text):
        """Muestra un dialogo con el error no controlado e indica en que carpeta quedo el detalle."""
        QMessageBox.critical(None, "Error inesperado",
                             f"{text}\n\nEl detalle quedó guardado en {LOGS_DIR}")

    install_exception_hook(notify_error)

    # Importaciones que requieren una QApplication creada (paleta, iconos, ventana)
    from app.ui.styles.palette import detect_dark_mode, get_colors
    from app.ui.styles.theme import apply_theme
    from app.ui import scale
    from app.ui.window import MainWindow

    # La escala se calcula antes de crear la interfaz para que todas las medidas la usen
    scale.init()
    apply_theme(app, get_colors(detect_dark_mode()))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
