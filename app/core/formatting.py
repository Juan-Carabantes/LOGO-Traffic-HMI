def format_mm_ss(seconds):
    """Formatea segundos como minutos y segundos, por ejemplo '1:20'."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def format_duration(time):
    """Formatea una duración como '00:45 s' o '02:10 min'; devuelve '' si nunca se activo."""
    if time <= 0:
        return ""
    if time < 60:
        return f"{int(time):02d}.{int((time % 1) * 10)} s"
    minutes, seconds = int(time // 60), int(time % 60)
    return f"{minutes:02d}:{seconds:02d} min"


def hex_to_bgr(color_hex, default=(255, 255, 255)):
    """Convierte #RRGGBB a tupla BGR para OpenCV."""
    try:
        value = str(color_hex).strip().lstrip("#")
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        return (b, g, r)
    except (ValueError, IndexError):
        return default
