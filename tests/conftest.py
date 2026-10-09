import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True, scope="session")
def temp_config(tmp_path_factory):
    """Copia app/config/ a una carpeta temporal para que las pruebas no modifiquen los .conf reales."""
    import app.core.app_config as module

    target = tmp_path_factory.mktemp("config")
    for file in (ROOT / "app" / "config").glob("*.conf"):
        shutil.copy(file, target / file.name)
    shutil.copytree(ROOT / "app" / "config" / "defaults", target / "defaults")
    # Redirige AppConfig a la copia y fuerza una instancia nueva
    module.CONFIG_DIR = target
    module.MASTER_FILE = target / "app.conf"
    module.AppConfig._instance = None
    yield target
