# -*- mode: python ; coding: utf-8 -*-
# --- Receta de PyInstaller para crear LOGO-Traffic-HMI.exe (un solo archivo) ---
# Se ejecuta con build.bat; no hace falta abrirla.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
WINDOWS = sys.platform == "win32"

# Recursos de solo lectura: configuración inicial y de fabrica, iconos, estilos y modelos
datas = [
    (str(ROOT / "app" / "config"), "app/config"),
    (str(ROOT / "app" / "assets"), "app/assets"),
    (str(ROOT / "app" / "ui" / "styles"), "app/ui/styles"),
]
models = ROOT / "models"
for item in models.glob("*"):
    if item.suffix == ".pt":
        datas.append((str(item), "models"))
    elif item.is_dir() and item.name.endswith("_openvino_model"):
        datas.append((str(item), f"models/{item.name}"))

# Librerias con archivos de datos, complementos o importaciones dinamicas
binaries, hiddenimports = [], []
for package in ("ultralytics", "openvino", "lap", "snap7", "pygrabber", "psutil"):
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

# Operaciones compiladas de torchvision (nms): PyInstaller no las detecta solas
import importlib.util
torchvision_dir = Path(importlib.util.find_spec("torchvision").origin).parent
for item in torchvision_dir.iterdir():
    if item.suffix in (".so", ".pyd", ".dll"):
        binaries.append((str(item), "torchvision"))

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "jupyter", "notebook", "tensorboard", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Pantalla de carga mientras el .exe se descomprime (solo en Windows)
splash_items = []
if WINDOWS:
    splash = Splash(
        str(ROOT / "packaging" / "splash.png"),
        binaries=a.binaries,
        datas=a.datas,
        text_pos=(40, 250),
        text_size=8,
        text_color="#5f6b7d",
        minify_script=True,
        always_on_top=False,
    )
    splash_items = [splash, splash.binaries]

exe = EXE(
    pyz,
    a.scripts,
    *splash_items,
    a.binaries,
    a.datas,
    [],
    name="LOGO-Traffic-HMI",
    console=False,                 # sin ventana negra de consola
    upx=False,                     # sin compresion UPX: menos falsos positivos del antivirus
    icon=str(ROOT / "packaging" / "app.ico") if WINDOWS else None,
    version=str(ROOT / "packaging" / "version_info.txt") if WINDOWS else None,
    runtime_tmpdir=None,
)
