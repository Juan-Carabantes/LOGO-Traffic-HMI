import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    """Devuelve la QApplication compartida por las pruebas del módulo."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def no_cameras(monkeypatch):
    """Evita buscar cámaras reales al crear la vista de configuración."""
    import app.ui.views.settings_view as view
    monkeypatch.setattr(view, "list_camera_devices", lambda: [])


def test_reset_only_its_area(app, monkeypatch):
    """Comprueba que restablecer "Fuente de video" no cambia otras áreas ni secciones."""
    from app.core.app_config import AppConfig
    from app.ui.views.settings_view import SettingsView

    cfg = AppConfig.get_instance()
    cfg.set("camera", "fps", 60)
    cfg.set("camera", "video_file", "C:/videos/prueba.mp4")
    cfg.set("camera", "hud", "show", False)              # otra área: no debe cambiar
    cfg.set("plc", "ip", "10.0.0.9")                     # otra sección: no debe cambiar

    view = SettingsView()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    card, fields, extra = next(a for a in view._areas if a[0].lbl_title.text() == "Fuente de video")
    view._reset_area(card, fields, extra)

    assert cfg.get("camera", "fps") == 30
    assert cfg.get_text("camera", "video_file", "x") == ""
    assert view.spin_fps.value() == 30
    assert cfg.get("camera", "hud", "show") is False
    assert cfg.get_text("plc", "ip") == "10.0.0.9"


def test_reset_update_interval(app, monkeypatch):
    """Comprueba que restablecer "Historial" devuelve update_interval a su valor de fabrica."""
    from app.core.app_config import AppConfig
    from app.ui.views.settings_view import SettingsView

    cfg = AppConfig.get_instance()
    cfg.set("analytics", "general", "update_interval", "5")
    view = SettingsView()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    card, fields, extra = next(a for a in view._areas if a[0].lbl_title.text() == "Historial")
    view._reset_area(card, fields, extra)
    assert cfg.get_text("analytics", "update_interval") == "auto"
    assert view.combo_refresh.currentData() == "auto"
