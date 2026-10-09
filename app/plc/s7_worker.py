import logging
import time
from queue import Empty, Queue

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.app_config import AppConfig

try:
    import snap7
    _Client = getattr(snap7, "Client", None) or snap7.client.Client
    SNAP7_AVAILABLE = True
except Exception:
    snap7 = None
    _Client = None
    SNAP7_AVAILABLE = False

_log = logging.getLogger(__name__)


# --- Manejo de bits ---

def read_bits(byte):
    """Convierte un byte en una lista de 8 booleanos, empezando por el bit 0."""
    return [bool((byte >> index) & 1) for index in range(8)]


def write_bit(byte, index, value):
    """Devuelve el byte con el bit indicado encendido o apagado."""
    return byte | (1 << index) if value else byte & ~(1 << index)


# --- Hilo de comunicación S7 ---

class S7Worker(QThread):
    """Hilo que se comunica con el Logo por Ethernet S7 sin bloquear la interfaz.

    Lee las entradas y salidas en bucle, envía los pulsos de Marcha, Paro y Cruce
    y lee el tiempo de los temporizadores. Los tiempos solo se leen, el Logo no
    permite escribirlos.
    """

    data_read = pyqtSignal(list, list, int, int)   # bits_q, bits_i, byte_q, byte_i
    connected = pyqtSignal(str)                    # ip
    disconnected = pyqtSignal(str, bool)           # motivo, fue_error
    order_sent = pyqtSignal(str)                   # texto de la orden
    times_read = pyqtSignal(dict)                  # {bloque: valor crudo de su VW}

    def __init__(self, ip, time_reads=None, parent=None):
        """Prepara el hilo con la IP del Logo y los parámetros de plc.conf."""
        super().__init__(parent)
        self.time_reads = dict(time_reads or {})   # {bloque: dirección VW}
        self.ip = ip
        self._active = True
        self._orders = Queue()

        # Parámetros de conexión y direcciones de memoria del Logo
        cfg = AppConfig.get_instance()
        self.tsap_local = int(cfg.get_text("plc", "tsap_local", "0x0300"), 16)
        self.tsap_remote = int(cfg.get_text("plc", "tsap_remote", "0x0200"), 16)
        self.rack = cfg.get("plc", "rack", default=0)
        self.slot = cfg.get("plc", "slot", default=1)
        self.port = cfg.get("plc", "port", default=102)
        self.db_number = cfg.get("plc", "db_number", default=1)
        self.inputs_byte = cfg.get("plc", "inputs_byte", default=1024)
        self.outputs_byte = cfg.get("plc", "outputs_byte", default=1064)
        self.markers_byte = cfg.get("plc", "markers_byte", default=1104)

        # Tiempos del ciclo de lectura y de los pulsos
        self.poll_ms = cfg.get("plc", "poll_interval_ms", default=100)
        self.pulse_ms = cfg.get("plc", "control_pulse_ms", default=100)
        self.stop_timeout_ms = cfg.get("plc", "stop_timeout_ms", default=1500)
        self.interval_times = max(0.5, float(cfg.get("plc", "timers", "read_interval_s", default=2)))

    # --- Ciclo principal ---

    def run(self):
        """Conecta con el Logo y lee entradas, salidas y tiempos hasta que se detiene."""
        if not SNAP7_AVAILABLE:
            self.disconnected.emit("python-snap7 no está instalado.", True)
            return

        # Conexión con el Logo
        client = _Client()
        try:
            client.set_connection_params(self.ip, self.tsap_local, self.tsap_remote)
            client.connect(self.ip, self.rack, self.slot, self.port)
        except Exception as error:
            self.disconnected.emit(f"No se pudo conectar a {self.ip}: {error}", True)
            return

        if not client.get_connected():
            self.disconnected.emit(f"Tiempo agotado al conectar con {self.ip}.", True)
            return

        # Bucle de lectura: órdenes pendientes, salidas, entradas y tiempos
        self.connected.emit(self.ip)
        reason, was_error = "Enlace cerrado por el usuario.", False
        next_read = 0.0
        while self._active:
            try:
                self._process_orders(client)
                byte_q = int(client.db_read(self.db_number, self.outputs_byte, 1)[0])
                try:
                    byte_i = int(client.db_read(self.db_number, self.inputs_byte, 1)[0])
                except Exception:
                    byte_i = 0
                self.data_read.emit(read_bits(byte_q), read_bits(byte_i), byte_q, byte_i)
                # Los tiempos se leen con menos frecuencia que las E/S
                if self.time_reads and time.time() >= next_read:
                    next_read = time.time() + self.interval_times
                    self._read_times(client)
            except Exception as error:
                reason, was_error = f"Pérdida de enlace: {error}", True
                break
            self.msleep(int(self.poll_ms))

        # Cierre de la conexión
        try:
            if client.get_connected():
                client.disconnect()
        except Exception:
            pass
        self.disconnected.emit(reason, was_error)

    def shutdown(self):
        """Detiene el ciclo y espera a que el hilo termine."""
        self._active = False
        self.wait(int(self.stop_timeout_ms))

    # --- Órdenes y lectura de tiempos ---

    def send_pulse(self, bit, text):
        """Encola un pulso sobre la marca indicada (M1=0, M2=1, M3=2)."""
        self._orders.put((int(bit), text))

    def _read_times(self, client):
        """Lee la palabra VW de 16 bits de cada temporizador sin cortar el enlace si falla."""
        values = {}
        for block, address in self.time_reads.items():
            try:
                data = client.db_read(self.db_number, address, 2)
                values[block] = int.from_bytes(bytes(data[:2]), "big")
            except Exception as error:
                _log.debug("No se pudo leer VW%s (%s): %s", address, block, error)
        if values:
            self.times_read.emit(values)

    def _process_orders(self, client):
        """Ejecuta los pulsos pendientes: enciende la marca, espera y la apaga."""
        while True:
            try:
                bit, text = self._orders.get_nowait()
            except Empty:
                return
            self._write_marker(client, bit, True)
            self.order_sent.emit(text)
            time.sleep(self.pulse_ms / 1000.0)
            self._write_marker(client, bit, False)

    def _write_marker(self, client, bit, value):
        """Cambia un solo bit del byte de marcas sin alterar los demás."""
        current = int(client.db_read(self.db_number, self.markers_byte, 1)[0])
        new = write_bit(current, bit, value)
        client.db_write(self.db_number, self.markers_byte, bytearray([new]))
