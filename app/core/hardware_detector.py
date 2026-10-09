import os

try:
    import psutil
except Exception:
    psutil = None

try:
    import torch
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False


def _cuda_available():
    """Indica si torch esta disponible y detecta una GPU CUDA."""
    try:
        return TORCH_AVAILABLE and torch.cuda.is_available()
    except Exception:
        return False


def inspect_system_hardware():
    """Analiza CPU, RAM y GPU para sugerir un perfil de rendimiento (reglas en vision.conf)."""
    from .app_config import AppConfig

    cfg = AppConfig.get_instance()
    rules = cfg.section("vision", "hardware_rules")

    # Recursos del equipo; si no se pueden medir se usan valores tipicos
    cpu_count = os.cpu_count() or 4
    try:
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        ram_gb = 8.0

    has_cuda = _cuda_available()
    gpu_name = "No detectada"
    if has_cuda:
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            gpu_name = "GPU CUDA"

    # Umbrales de vision.conf -> [hardware_rules]; con CUDA siempre se usa el perfil alto
    high_threads = rules.get("high_min_threads", 12)
    high_ram = rules.get("high_min_ram_gb", 16)
    medium_threads = rules.get("medium_min_threads", 6)
    medium_ram = rules.get("medium_min_ram_gb", 8)

    if has_cuda or (cpu_count >= high_threads and ram_gb >= high_ram):
        suggested_profile = "high"
    elif cpu_count >= medium_threads and ram_gb >= medium_ram:
        suggested_profile = "medium"
    else:
        suggested_profile = "low"

    return {
        "cpu_count": cpu_count,
        "ram_gb": ram_gb,
        "has_cuda": has_cuda,
        "gpu_name": gpu_name,
        "suggested_profile": suggested_profile,
    }


# Perfil de respaldo si vision.conf no define el perfil pedido
_FALLBACK_PROFILE = {
    "name": "Medio",
    "imgsz": 640,
    "device": "cpu",
    "model": "yolo26n.pt",
    "max_det": 60,
    "update_interval_s": 2,
    "ai_max_fps": 0,
}


def get_profile_settings(profile_name):
    """Devuelve los parámetros de inferencia del perfil definido en vision.conf -> [profile_*]."""
    from .app_config import AppConfig

    cfg = AppConfig.get_instance()
    name = str(profile_name or "medium").lower()
    if name == "auto":
        name = cfg.hardware_info.get("suggested_profile", "medium")

    profile = cfg.section("vision", f"profile_{name}") or cfg.section("vision", "profile_medium")
    result = dict(_FALLBACK_PROFILE)
    result.update(profile)

    # Solo se usa la GPU si el perfil la pide y CUDA esta disponible
    device = str(result.get("device", "cpu")).lower()
    result["device"] = "0" if device in ("gpu", "cuda", "0") and _cuda_available() else "cpu"

    return result


# --- Frecuencia de actualización de datos ---

# Opciones de analytics.conf [general] update_interval (en segundos, o realtime / auto)
REALTIME_MS = 500


def active_profile_name():
    """Devuelve el perfil en uso (low, medium o high), resolviendo "auto" con el hardware detectado."""
    from .app_config import AppConfig

    cfg = AppConfig.get_instance()
    name = str(cfg.get_text("vision", "profile", "auto")).lower()
    if name == "auto":
        name = cfg.hardware_info.get("suggested_profile", "medium")
    return name


def update_interval_ms():
    """Intervalo de actualización de los datos en pantalla en milisegundos.

    auto usa el del perfil de rendimiento (update_interval_s), realtime refresca cada
    medio segundo y un número fija los segundos entre actualizaciones.
    """
    from .app_config import AppConfig

    cfg = AppConfig.get_instance()
    value = str(cfg.get_text("analytics", "update_interval", "auto")).strip().lower()
    if value == "realtime":
        return REALTIME_MS
    try:
        if value in ("", "auto"):
            seconds = float(get_profile_settings(active_profile_name()).get("update_interval_s", 1))
        else:
            seconds = float(value)
    except (TypeError, ValueError):
        seconds = 1.0
    return int(max(0.25, seconds) * 1000)

