import time
from dataclasses import dataclass, field

SEVERITIES = ("info", "warning", "critical")


@dataclass
class Alarm:
    """Alarma activa con su código, texto, severidad, inicio y estado de reconocimiento."""

    code: str
    text: str
    severity: str = "warning"
    start: float = field(default_factory=time.time)
    acked: bool = False


class AlarmManager:
    """Gestor de alarmas del sistema, sin dependencias de Qt.

    Cada alarma tiene un código único; mientras siga activa no se repite. Los
    observadores (interfaz, historial, bitácora) reciben cada cambio.

        alarms = AlarmManager()
        alarms.subscribe(lambda event, alarm: ...)
        alarms.activate("plc_link", "Se perdio el enlace con el Logo", "critical")
        alarms.deactivate("plc_link")

    Severidades: info | warning | critical. Los umbrales están en analytics.conf -> [alarms].
    """

    def __init__(self):
        """Inicia sin alarmas activas ni observadores."""
        self.active = {}
        self._observers = []
        self._conditions = {}   # código -> momento en que la condición empezó (para retardos)

    def subscribe(self, callback):
        """Registra callback(event, alarm) con event = 'activated' | 'deactivated' | 'acked'."""
        self._observers.append(callback)

    def _notify(self, evt, alarm):
        """Avisa a cada observador; un observador que falla no afecta a los demás."""
        for callback in list(self._observers):
            try:
                callback(evt, alarm)
            except Exception:
                pass

    def activate(self, code, text, severity="warning"):
        """Activa la alarma si no estaba activa; devuelve True si se activo."""
        if code in self.active:
            return False
        alarm = Alarm(code, text, severity if severity in SEVERITIES else "warning")
        self.active[code] = alarm
        self._notify("activated", alarm)
        return True

    def deactivate(self, code):
        """Desactiva la alarma y olvida su condición; devuelve True si estaba activa."""
        self._conditions.pop(code, None)
        alarm = self.active.pop(code, None)
        if alarm is not None:
            self._notify("deactivated", alarm)
            return True
        return False

    def evaluate(self, code, condition, text, severity="warning", delay_s=0.0, now=None):
        """Activa la alarma si la condición se mantiene al menos delay_s; si no, la desactiva."""
        now = now if now is not None else time.time()
        if not condition:
            self.deactivate(code)
            return
        start = self._conditions.setdefault(code, now)
        if now - start >= delay_s:
            self.activate(code, text, severity)

    def ack_all(self):
        """Marca como reconocidas todas las alarmas activas."""
        for alarm in self.active.values():
            if not alarm.acked:
                alarm.acked = True
                self._notify("acked", alarm)

    @property
    def unacked(self):
        """Devuelve el número de alarmas activas sin reconocer."""
        return sum(1 for a in self.active.values() if not a.acked)

    @property
    def max_severity(self):
        """Devuelve la severidad más alta entre las alarmas activas, o None si no hay."""
        if not self.active:
            return None
        return max(self.active.values(), key=lambda a: SEVERITIES.index(a.severity)).severity
