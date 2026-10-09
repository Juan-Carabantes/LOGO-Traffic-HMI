from collections import deque
import time

from ..core.app_config import AppConfig


class TrafficAnalyzer:
    """Calcula densidad, caudal de tráfico y tiempos sugeridos para los bloques del Logo.

    Los tiempos son solo informativos; todas las reglas y umbrales están en analytics.conf.
    """

    def __init__(self):
        """Inicia sin cruces registrados y carga las reglas."""
        self.crossings_timestamps = deque()
        self.reload_rules()

    def reload_rules(self):
        """Lee o vuelve a leer las reglas desde analytics.conf."""
        cfg = AppConfig.get_instance()
        general = cfg.section("analytics", "general")
        self.window_s = float(general.get("history_window_s", 300))
        self.max_capacity = float(general.get("max_vehicles", 8))

        # Una sección de reglas por bloque de temporizador
        self.rules_green = cfg.section("analytics", "green_B3")
        self.rules_yellow = cfg.section("analytics", "yellow_B21")
        self.rules_red = cfg.section("analytics", "red_nowait_B6")
        self.rules_pedestrian = cfg.section("analytics", "red_wait_B13")
        self.rules_fixed = cfg.section("analytics", "fixed")

    # --- Caudal y densidad ---

    def record_crossing(self, timestamp=None):
        """Registra el cruce de un vehículo y descarta los que salieron de la ventana."""
        self.crossings_timestamps.append(timestamp or time.time())
        self._clean_old_records()

    def _clean_old_records(self):
        """Elimina los cruces más antiguos que history_window_s."""
        cutoff = time.time() - self.window_s
        while self.crossings_timestamps and self.crossings_timestamps[0] < cutoff:
            self.crossings_timestamps.popleft()

    def get_flow_rate_per_minute(self):
        """Devuelve los vehículos que cruzaron la línea durante el último minuto."""
        self._clean_old_records()
        one_min_ago = time.time() - 60.0
        return sum(1 for t in self.crossings_timestamps if t >= one_min_ago)

    def get_projected_flow_per_hour(self):
        """Proyecta el caudal por hora a partir del último minuto."""
        return self.get_flow_rate_per_minute() * 60

    def calculate_traffic_density(self, active_vehicle_count):
        """Devuelve el nivel de saturación de la via (0 % a 100 %) respecto a max_vehicles."""
        capacity = max(1.0, self.max_capacity)
        percent = (min(active_vehicle_count, capacity) / capacity) * 100.0
        return round(percent, 1)

    # --- Reglas por bloque ---

    @staticmethod
    def _levels(rules):
        """Devuelve la lista ordenada de valores 'level_N' de una sección."""
        keys = sorted(
            (k for k in rules if k.startswith("level_")),
            key=lambda k: int(k.split("_")[1]) if k.split("_")[1].isdigit() else 0,
        )
        levels = []
        for key in keys:
            value = rules[key]
            levels.append(value if isinstance(value, list) else [value])
        return levels

    def _green_seconds(self, flow_min, active, speed):
        """Calcula el verde (B3) según caudal y vehículos en escena, con extra por congestion lenta."""
        r = self.rules_green
        seconds = r.get("saturation", 80)
        # Primer nivel que cumple caudal y vehículos; si ninguno, se usa saturation
        for level in self._levels(r):
            if len(level) >= 3 and flow_min <= level[0] and active <= level[1]:
                seconds = level[2]
                break
        speed_threshold = r.get("congestion_speed_kmh", 15)
        if 0 < speed < speed_threshold and active >= r.get("congestion_min_vehicles", 3):
            seconds = min(r.get("max_s", 90), seconds + r.get("congestion_extra_s", 15))
        return int(seconds)

    def _yellow_seconds(self, speed):
        """Calcula el amarillo (B21) según la velocidad media."""
        r = self.rules_yellow
        if speed > r.get("high_speed_kmh", 50):
            return int(r.get("seconds_high", 5))
        if speed > r.get("medium_speed_kmh", 30):
            return int(r.get("seconds_medium", 4))
        return int(r.get("seconds_low", 3))

    def _red_seconds(self, flow_min):
        """Calcula el rojo sin espera (B6) según el caudal."""
        r = self.rules_red
        for level in self._levels(r):
            if len(level) >= 2 and flow_min <= level[0]:
                return int(level[1])
        return int(r.get("seconds_high", 50))

    def _pedestrian_seconds(self, active):
        """Calcula el rojo con espera peatonal (B13) según los vehículos en escena."""
        r = self.rules_pedestrian
        if active >= r.get("congestion_vehicles", 5):
            return int(r.get("seconds_congestion", 55))
        return int(r.get("seconds_normal", 45))

    def calculate_suggested_timers(self, active_vehicle_count=0, avg_speed_kmh=0.0):
        """Devuelve las sugerencias en segundos y en texto ('Sugerencia: 1:20 min') para cada bloque."""
        flow_min = self.get_flow_rate_per_minute()
        green = self._green_seconds(flow_min, active_vehicle_count, avg_speed_kmh)
        yellow = self._yellow_seconds(avg_speed_kmh)
        red = self._red_seconds(flow_min)
        pedestrian = self._pedestrian_seconds(active_vehicle_count)
        # Los parpadeos son tiempos fijos de analytics.conf [fixed]; ConfFile puede guardar la clave en minusculas
        fixed = {str(k).lower(): v for k, v in self.rules_fixed.items()}
        blink_b11 = float(fixed.get("blink_b11", 3))
        blink_b16 = float(fixed.get("blink_b16", 5))

        def item(seconds, reason, fixed=False):
            """Arma la sugerencia de un bloque con sus segundos, texto, motivo y si es un tiempo fijo."""
            return {"seconds": seconds, "text": self.format_time_suggestion(seconds), "reason": reason,
                    "fixed": fixed}

        return {
            "B3": item(green, f"Caudal actual: {flow_min} veh/min"),
            "B21": item(yellow, f"Velocidad: {int(avg_speed_kmh)} km/h"),
            "B6": item(red, "Ciclo balanceado de flujo"),
            "B13": item(pedestrian, "Evacuación peatonal segura"),
            "B11": item(blink_b11, "Parpadeo: tiempo fijo, no depende del tráfico", fixed=True),
            "B16": item(blink_b16, "Parpadeo: tiempo fijo, no depende del tráfico", fixed=True),
        }

    @staticmethod
    def format_time_suggestion(seconds):
        """Devuelve 'Sugerencia: 1:20 min' o 'Sugerencia: 0:45 min'."""
        minutes, secs = divmod(int(seconds), 60)
        return f"Sugerencia: {minutes}:{secs:02d} min"
