import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.vision.model_engine import rect_size  # noqa: E402

MODELS_DIR = ROOT / "models"

# --- Modelos que se incluyen en el .exe ---

# (modelo, lado de análisis) de cada perfil: bajo y medio usan yolo26n, alto yolo26s
PROFILES = (("yolo26n.pt", 480), ("yolo26n.pt", 640), ("yolo26s.pt", 640))
# Proporciones de video más comunes: 16:9 (1280x720) y 4:3 (640x480)
RATIOS = ((1280, 720), (640, 480))


def main():
    """Descarga los .pt y deja listas las versiones OpenVINO para que el .exe funcione sin internet."""
    from ultralytics import YOLO

    MODELS_DIR.mkdir(exist_ok=True)
    for name, side in PROFILES:
        weights = MODELS_DIR / name
        if not weights.exists():
            print(f"Descargando {name}...")
            YOLO(name)                                   # ultralytics lo descarga en la carpeta actual
            shutil.move(name, weights)
        stem = Path(name).stem
        for width, height in RATIOS:
            h, w = rect_size(side, width, height)
            target = MODELS_DIR / f"{stem}_{h}x{w}_openvino_model"
            if (target / f"{stem}.xml").exists():
                print(f"Ya existe {target.name}")
                continue
            print(f"Optimizando {stem} para {w}x{h} (OpenVINO)...")
            exported = Path(YOLO(str(weights)).export(format="openvino", imgsz=[h, w], dynamic=False, verbose=False))
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(exported), str(target))
    print("Modelos listos en", MODELS_DIR)


if __name__ == "__main__":
    main()
