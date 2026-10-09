import logging
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core.app_config import AppConfig
from ..core.io_map import load_signals
from ..core.settings import DATABASE_PATH
from ..core.timers_map import load_timer_blocks
from .connection_history import ConnectionHistory
from .s7_worker import S7Worker

_log = logging.getLogger(__name__)

# Lógica del programa del Logo (índice de bit dentro del byte de salidas)
BIT_GREEN, BIT_YELLOW, BIT_RED, BIT_ACTIVE, BIT_STOP = 0, 1, 2, 3, 4

# Órdenes remotas: texto para la bitácora, clave en plc.conf -> [control_bits] y bit por defecto
ORDERS = {
    "start": ("MARCHA (M1)", "start", 0),
    "stop": ("PARO (M2)", "stop", 1),
    "pedestrian": ("CRUCE PEATONAL (M3)", "pedestrian", 2),
}


class PlcController(QObject):
    """Controlador del Logo: estados de conexión, interpretación de E/S y bitácora.

    La interfaz solo escucha las señales de este objeto; no conoce snap7 ni bytes.
    Las órdenes posibles son Marcha, Paro y Cruce peatonal. Los tiempos de los
    temporizadores solo se leen (si están asignados a VM); nunca se escriben.

    Estados de conexión:  disconnected | connecting | connected | reconnecting | error
    Estados del circuito: neutral | success | warning | error (con texto)
    """

    connection_state = pyqtSignal(str, str)        # estado, texto para mostrar
    circuit_state = pyqtSignal(str, str)           # tipo, texto
    lights = pyqtSignal(bool, bool, bool)          # verde, amarillo, rojo
    io_updated = pyqtSignal(list, list)            # bits_q, bits_i
    message = pyqtSignal(str)                      # línea para la bitácora
    logo_times = pyqtSignal(dict)                  # {bloque: segundos} leídos del Logo

    def __init__(self, parent=None):
        """Prepara el historial de conexiones, la IP guardada y el temporizador de reintento."""
        super().__init__(parent)
        self.cfg = AppConfig.get_instance()
        self.history = ConnectionHistory(DATABASE_PATH)
        self.worker = None
        self.state = "disconnected"
        self.ip = self.cfg.get_text("plc", "ip", "192.168.0.3")
        self._last_q = self._last_i = -1
        self._manual_disconnect = False
        self._had_link = False   # solo se reintenta si el enlace llegó a establecerse

        # Temporizador de un solo disparo para la reconexión automática
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._retry)

    # --- API publica ---

    @property
    def connected(self):
        """Indica si el enlace S7 esta activo."""
        return self.state == "connected"

    def toggle(self, ip=None):
        """Desconecta si hay enlace o intento en curso; si no, conecta."""
        if self.state in ("connected", "connecting", "reconnecting"):
            self.disconnect_plc()
        else:
            self.connect_to(ip)

    def connect_to(self, ip=None):
        """Guarda la IP en plc.conf e inicia la conexión con el Logo."""
        ip = (ip or self.ip or "").strip()
        if not ip:
            self._log("Escribe la IP del LOGO! antes de conectar.")
            return
        self.ip = ip
        self.cfg.set("plc", "ip", ip)
        self._manual_disconnect = False
        self._had_link = False
        self._start_worker("connecting", f"Conectando a {ip}…")

    def disconnect_plc(self):
        """Desconecta a petición del usuario y cancela los reintentos."""
        self._manual_disconnect = True
        self._retry_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.shutdown()
        else:
            self._change_state("disconnected", "Desconectado")

    def send_order(self, name):
        """Envia una orden: 'start' | 'stop' | 'pedestrian' (bits en plc.conf -> [control_bits])."""
        if not self.connected or name not in ORDERS:
            return
        text, key, default_bit = ORDERS[name]
        bit = self.cfg.get("plc", key, default=default_bit)
        self.worker.send_pulse(bit, text)

    def update_reads(self):
        """Aplica cambios de vw_read de timers.conf sin reconectar."""
        if self.worker and self.worker.isRunning():
            self.worker.time_reads = self._configured_reads()

    def _configured_reads(self):
        """Devuelve {bloque: VW} de los temporizadores con vw_read > 0, si la lectura esta activa."""
        if not self.cfg.get("plc", "timers", "read_times", default=True):
            return {}
        return {b.id: b.vw_read for b in load_timer_blocks() if b.vw_read > 0}

    def shutdown(self):
        """Detiene el hilo y los reintentos; se llama al cerrar la aplicación."""
        self._manual_disconnect = True
        self._retry_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.shutdown()

    # --- Hilo de comunicación ---

    def _start_worker(self, state, text):
        """Crea el S7Worker, conecta sus señales y lo inicia si no hay otro en marcha."""
        if self.worker and self.worker.isRunning():
            return
        self._change_state(state, text)
        self.worker = S7Worker(self.ip, self._configured_reads())
        self.worker.times_read.connect(self._on_times)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.data_read.connect(self._on_data)
        self.worker.order_sent.connect(lambda t: self._log(f"Orden enviada: {t}"))
        self.worker.start()

    def _on_connected(self, ip):
        """Marca el enlace como activo y registra la IP en el historial."""
        self._had_link = True
        self._last_q = self._last_i = -1
        self._change_state("connected", "S7 activo")
        self._log(f"Enlace S7 activo con {ip}")
        try:
            self.history.record_connection(ip, datetime.now().isoformat(timespec="seconds"))
        except Exception as error:
            _log.warning("No se pudo guardar el historial de conexión: %s", error)

    def _on_disconnected(self, reason, was_error):
        """Apaga las luces e indicadores y decide si se reintenta la conexión."""
        self._log(reason)
        self.lights.emit(False, False, False)
        self.io_updated.emit([False] * 8, [False] * 8)
        self.circuit_state.emit("neutral", "Sin enlace")

        # Solo se reintenta tras un error en un enlace que llegó a establecerse
        retry = (
            was_error
            and self._had_link
            and not self._manual_disconnect
            and self.cfg.get("plc", "auto_reconnect", default=True)
        )
        if retry:
            seconds = max(1, int(self.cfg.get("plc", "retry_s", default=5)))
            self._change_state("reconnecting", f"Reintento en {seconds} s")
            self._retry_timer.start(seconds * 1000)
        elif was_error:
            self._change_state("error", "Error de enlace")
        else:
            self._change_state("disconnected", "Desconectado")

    def _retry(self):
        """Vuelve a conectar si el usuario no desconecto manualmente."""
        if not self._manual_disconnect:
            self._start_worker("reconnecting", f"Reconectando a {self.ip}…")

    def _on_data(self, bits_q, bits_i, byte_q, byte_i):
        """Interpreta las E/S leidas: luces, estado del circuito y registro de cambios."""
        green, yellow, red = bits_q[BIT_GREEN], bits_q[BIT_YELLOW], bits_q[BIT_RED]
        active, stop = bits_q[BIT_ACTIVE], bits_q[BIT_STOP]

        # Con el circuito en paro las luces se muestran apagadas
        if stop and not active:
            self.lights.emit(False, False, False)
        else:
            self.lights.emit(green, yellow, red)

        # Estado del circuito; todo en cero indica que el Logo esta en STOP
        if byte_q == 0 and byte_i == 0:
            self.circuit_state.emit("error", "LOGO! en STOP")
        elif stop and not active:
            self.circuit_state.emit("warning", "Semáforo en paro")
        elif active:
            self.circuit_state.emit("success", "Semáforo en marcha")

        self.io_updated.emit(bits_q, bits_i)

        # Solo se escribe en la bitácora cuando cambia algún byte
        if byte_q != self._last_q or byte_i != self._last_i:
            self._last_q, self._last_i = byte_q, byte_i
            outputs, inputs = load_signals()
            q = [s.log for s in outputs if s.log and bits_q[s.bit]]
            i = [s.log for s in inputs if s.log and bits_i[s.bit]]
            self._log(f"[S7] Salidas: {', '.join(q) or 'OFF'} | Entradas: {', '.join(i) or 'OFF'}")

    def _on_times(self, raw):
        """Convierte los valores crudos de VW a segundos con el factor de plc.conf."""
        factor = max(1e-6, float(self.cfg.get("plc", "timers", "factor", default=100)))
        self.logo_times.emit({block: round(value / factor, 2) for block, value in raw.items()})

    # --- Estado y bitácora ---

    def _change_state(self, state, text):
        """Actualiza el estado de conexión y lo emite a la interfaz."""
        self.state = state
        self.connection_state.emit(state, text)

    def _log(self, text):
        """Escribe el texto en el log y lo envía a la bitácora de la interfaz."""
        _log.info(text)
        self.message.emit(text)
