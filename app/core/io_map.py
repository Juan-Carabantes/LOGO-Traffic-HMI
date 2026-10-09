from dataclasses import dataclass

from .app_config import AppConfig


VALID_COLORS = ("green", "yellow", "red", "cyan", "orange", "blue")


@dataclass(frozen=True)
class Signal:
    """Entrada o salida digital del Logo definida en una sección de io.conf."""

    code: str          # "Q1", "I3", ...
    kind: str          # "output" | "input"
    bit: int           # 0..7 dentro del byte leído
    name: str
    color: str
    visible: bool = True
    log: str = ""
    stopwatch: bool = False

    @property
    def is_output(self):
        """Indica si la señal es una salida."""
        return self.kind == "output"


def load_signals(only_visible=False):
    """Devuelve (salidas, entradas) en el orden en que aparecen en io.conf."""
    cfg = AppConfig.get_instance()
    outputs, inputs = [], []
    for code in cfg.sections("io"):
        data = cfg.section("io", code)
        kind = str(data.get("kind", "")).lower()
        if kind not in ("output", "input"):
            continue  # secciones sin señal, como [layout]

        color = str(data.get("color", "blue")).lower()
        signal = Signal(
            code=code,
            kind=kind,
            bit=max(0, min(7, int(data.get("bit", 0)))),
            name=str(data.get("name", code)),
            color=color if color in VALID_COLORS else "blue",
            visible=bool(data.get("visible", True)),
            log=str(data.get("log", "") or ""),
            stopwatch=bool(data.get("stopwatch", kind == "output")),
        )
        if only_visible and not signal.visible:
            continue
        (outputs if signal.is_output else inputs).append(signal)
    return outputs, inputs


def layout_io():
    """Devuelve los parámetros de la sección [layout] de io.conf."""
    data = AppConfig.get_instance().section("io", "layout")
    return {
        "output_columns": max(1, int(data.get("output_columns", 3))),
        "input_columns": max(1, int(data.get("input_columns", 3))),
        "outputs_title": str(data.get("outputs_title", "Salidas Digitales (Q)")),
        "inputs_title": str(data.get("inputs_title", "Entradas Digitales (I)")),
    }
