from dataclasses import dataclass

from .app_config import AppConfig


@dataclass(frozen=True)
class TimerBlock:
    """Bloque de temporizador del Logo definido en timers.conf (solo lectura).

    El Logo no permite cambiar los tiempos desde la app; se usan en Estadísticas para
    comparar el tiempo actual de cada bloque con el recomendado según el tráfico.
    Si vw_read > 0 el tiempo actual se lee del Logo (LogoSoft Comfort: Herramientas >
    Asignación de parámetros a VM, parámetro T del temporizador); si no, se usa seconds.
    """

    id: str
    name: str
    description: str
    seconds: int          # tiempo programado (referencia si no se lee del Logo)
    output: str
    in_analytics: bool
    reason: str
    vw_read: int = 0      # dirección VW donde el Logo publica el parámetro T (0 = no leer)

    @property
    def function(self):
        """Devuelve el nombre con su salida, por ejemplo 'Timer Verde (Q1)'."""
        return f"{self.name} ({self.output})" if self.output else self.name


def load_timer_blocks(only_analytics=False):
    """Devuelve la lista de bloques en el orden de timers.conf."""
    cfg = AppConfig.get_instance()
    blocks = []
    for block_id in cfg.sections("timers"):
        d = cfg.section("timers", block_id)
        block = TimerBlock(
            id=block_id,
            name=str(d.get("name", block_id)),
            description=str(d.get("description", "")),
            seconds=int(d.get("seconds", 30)),
            output=str(d.get("output", "")),
            in_analytics=bool(d.get("in_analytics", False)),
            reason=str(d.get("reason", "")),
            vw_read=int(d.get("vw_read", 0) or 0),
        )
        if only_analytics and not block.in_analytics:
            continue
        blocks.append(block)
    return blocks
