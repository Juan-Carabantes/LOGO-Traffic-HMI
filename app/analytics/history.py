import csv
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from ..core.app_config import AppConfig
from ..core.settings import DATA_DIR

_log = logging.getLogger(__name__)

# Tablas del historial:
#   crossings  un registro por vehículo que cruza una línea (hora, línea, sentido, clase, velocidad)
#   hourly     totales por hora y tipo de vehículo (se actualiza al guardar los cruces)
#   samples    un resumen por minuto (vehículos en escena, ocupación, velocidad media, detenidos)
#   alarms     alarmas activadas y cuando terminaron
_SCHEMA = """
CREATE TABLE IF NOT EXISTS crossings (
    ts REAL NOT NULL,
    line TEXT NOT NULL,
    direction INTEGER NOT NULL,
    cls TEXT NOT NULL,
    speed REAL,
    is_new INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_crossings_ts ON crossings(ts);
CREATE TABLE IF NOT EXISTS hourly (
    hour REAL NOT NULL,
    cls TEXT NOT NULL,
    vehicles INTEGER NOT NULL DEFAULT 0,
    speed_sum REAL NOT NULL DEFAULT 0,
    speed_n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hour, cls)
);
CREATE TABLE IF NOT EXISTS samples (
    ts REAL PRIMARY KEY,
    in_scene REAL,
    occupancy REAL,
    speed REAL,
    stopped REAL
);
CREATE TABLE IF NOT EXISTS alarms (
    ts_start REAL NOT NULL,
    ts_end REAL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alarms_ts ON alarms(ts_start);
"""

WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


def _day_start(date):
    """Devuelve la medianoche del día de la fecha indicada."""
    return datetime(date.year, date.month, date.day)


def hour_start(ts):
    """Devuelve el inicio, en hora local, de la hora que contiene ts."""
    return datetime.fromtimestamp(ts).replace(minute=0, second=0, microsecond=0).timestamp()


# Suma los cruces nuevos al total de su hora y clase
_UPSERT = """INSERT INTO hourly (hour, cls, vehicles, speed_sum, speed_n) VALUES (?,?,?,?,?)
ON CONFLICT(hour, cls) DO UPDATE SET vehicles = vehicles + excluded.vehicles,
    speed_sum = speed_sum + excluded.speed_sum, speed_n = speed_n + excluded.speed_n"""


def period_range(period, now=None):
    """Convierte un periodo 'today' | '7d' | '30d' en (since_ts, until_ts)."""
    now = now or datetime.now()
    if period == "today":
        since = _day_start(now)
    elif period == "30d":
        since = _day_start(now) - timedelta(days=29)
    else:
        since = _day_start(now) - timedelta(days=6)
    return since.timestamp(), now.timestamp()


class HistoryStore:
    """Historial de tráfico en SQLite (data/traffic_history.sqlite3) seguro entre hilos.

    Usa un solo archivo SQLite protegido con un candado. Las gráficas leen la tabla hourly
    (a lo sumo 24 filas por día y tipo), así las estadísticas se pueden refrescar cada
    segundo aunque haya meses de datos. La retención se define en analytics.conf ->
    [history] retention_days.
    """

    def __init__(self, path=None):
        """Abre o crea la base de datos, aplica el esquema y borra los datos vencidos."""
        self.path = path or (DATA_DIR / "traffic_history.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()
        self._pending = []
        self._minute_samples = []
        self._current_minute = None
        self.clear_old()

    # --- Escritura ---

    def record_crossings(self, events):
        """Acumula los cruces en memoria hasta el siguiente flush()."""
        with self._lock:
            self._pending.extend(
                (e["timestamp"], e.get("line", "line_1"), int(e.get("direction", 1)),
                 str(e.get("class", "other")).lower(), float(e.get("speed_kmh", 0) or 0),
                 1 if e.get("new_vehicle", True) else 0)
                for e in events
            )

    def record_sample(self, stats):
        """Acumula estadísticas y guarda un promedio por minuto al cambiar de minuto."""
        minute = int(time.time() // 60 * 60)
        with self._lock:
            if self._current_minute is not None and minute != self._current_minute and self._minute_samples:
                n = len(self._minute_samples)
                avg = [sum(m[i] for m in self._minute_samples) / n for i in range(4)]
                self._db.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?)", (self._current_minute, *avg))
                self._minute_samples = []
            self._current_minute = minute
            self._minute_samples.append((
                float(stats.get("vehicles_in_scene", 0)), float(stats.get("density_pct", 0)),
                float(stats.get("avg_speed", 0)), float(stats.get("stopped", 0)),
            ))

    def record_alarm(self, code, severity, text, active):
        """Registra el inicio de una alarma o cierra la que sigue abierta con ese código."""
        with self._lock:
            if active:
                self._db.execute("INSERT INTO alarms VALUES (?,?,?,?,?)", (time.time(), None, code, severity, text))
            else:
                self._db.execute(
                    "UPDATE alarms SET ts_end=? WHERE code=? AND ts_end IS NULL", (time.time(), code))
            self._db.commit()

    def flush(self):
        """Escribe en disco los cruces pendientes y actualiza los totales por hora."""
        with self._lock:
            if not self._pending:
                return
            self._db.executemany("INSERT INTO crossings VALUES (?,?,?,?,?,?)", self._pending)
            # Solo los vehículos nuevos suman al total por hora
            self._db.executemany(_UPSERT, [
                (hour_start(ts), cls_name, 1, speed if speed > 0 else 0.0, 1 if speed > 0 else 0)
                for ts, _, _, cls_name, speed, new in self._pending if new
            ])
            self._pending = []
            self._db.commit()

    def clear_old(self):
        """Borra los registros más antiguos que retention_days (0 = conservar siempre)."""
        days = int(AppConfig.get_instance().get("analytics", "retention_days", default=180) or 0)
        if days <= 0:
            return
        limit = time.time() - days * 86400
        with self._lock:
            for table, field in (("crossings", "ts"), ("hourly", "hour"), ("samples", "ts"),
                                 ("alarms", "ts_start")):
                self._db.execute(f"DELETE FROM {table} WHERE {field} < ?", (limit,))
            self._db.commit()

    def close(self):
        """Guarda los cruces pendientes y cierra la base de datos."""
        self.flush()
        with self._lock:
            self._db.close()

    # --- Consultas ---

    def _query(self, sql, params=()):
        """Ejecuta una consulta con el candado y devuelve todas las filas."""
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # Todas las consultas de gráficas usan la tabla hourly (rápido)
    _RANGE = "hour >= ? AND hour <= ?"

    def _range(self, since, until):
        """Ajusta el inicio del rango al comienzo de su hora."""
        return hour_start(since), until

    def days_with_data(self, since, until):
        """Cuenta los días con datos en el periodo (mínimo 1 para poder dividir)."""
        rows = self._query(
            f"SELECT COUNT(DISTINCT date(hour,'unixepoch','localtime')) FROM hourly WHERE {self._RANGE}",
            self._range(since, until))
        return max(1, rows[0][0] or 0)

    def by_hour_of_day(self, since, until):
        """Devuelve el promedio de vehículos por cada hora del día (0-23) en el periodo."""
        rows = self._query(
            "SELECT CAST(strftime('%H', hour, 'unixepoch', 'localtime') AS INTEGER), SUM(vehicles) "
            f"FROM hourly WHERE {self._RANGE} GROUP BY 1", self._range(since, until))
        days = self.days_with_data(since, until)
        values = [0.0] * 24
        for hour, count in rows:
            values[hour] = count / days
        return values

    def trend(self, since, until, by="hour"):
        """Devuelve la serie temporal (etiqueta, cantidad) por hora o por día, incluyendo huecos."""
        fmt, step = ("%Y-%m-%d %H", 3600) if by == "hour" else ("%Y-%m-%d", 86400)
        rows = dict(self._query(
            f"SELECT strftime('{fmt}', hour, 'unixepoch', 'localtime'), SUM(vehicles) "
            f"FROM hourly WHERE {self._RANGE} GROUP BY 1", self._range(since, until)))
        series = []
        t = datetime.fromtimestamp(since)
        end = datetime.fromtimestamp(until)
        while t <= end:
            key = t.strftime(fmt)
            label = t.strftime("%H:00") if by == "hour" else f"{WEEKDAYS[t.weekday()]} {t:%d}"
            series.append((label, rows.get(key, 0)))
            t += timedelta(seconds=step)
        return series

    def heatmap(self, since, until):
        """Devuelve una matriz 7x24 con el promedio de vehículos por día de la semana y hora."""
        rows = self._query(
            "SELECT CAST(strftime('%w', hour, 'unixepoch', 'localtime') AS INTEGER), "
            "CAST(strftime('%H', hour, 'unixepoch', 'localtime') AS INTEGER), "
            "SUM(vehicles), COUNT(DISTINCT date(hour, 'unixepoch', 'localtime')) "
            f"FROM hourly WHERE {self._RANGE} GROUP BY 1, 2", self._range(since, until))
        matrix = [[0.0] * 24 for _ in range(7)]
        for sql_day, hour, count, days in rows:
            day = (sql_day + 6) % 7  # SQLite: 0=domingo -> 0=lunes
            matrix[day][hour] = count / max(1, days)
        return matrix

    def by_class(self, since, until):
        """Devuelve {clase: total de vehículos} en el periodo."""
        return dict(self._query(
            f"SELECT cls, SUM(vehicles) FROM hourly WHERE {self._RANGE} GROUP BY cls",
            self._range(since, until)))

    def summary(self, since, until):
        """Resume el periodo: total, velocidad media, hora pico, promedio diario y ocupación."""
        total, speed_sum, with_speed = self._query(
            f"SELECT SUM(vehicles), SUM(speed_sum), SUM(speed_n) FROM hourly WHERE {self._RANGE}",
            self._range(since, until))[0]
        by_hour = self.by_hour_of_day(since, until)
        peak = max(range(24), key=lambda h: by_hour[h]) if any(by_hour) else None
        occupancy = self._query("SELECT AVG(occupancy) FROM samples WHERE ts BETWEEN ? AND ?", (since, until))[0][0]
        total = total or 0
        return {
            "total": total,
            "speed": (speed_sum / with_speed) if with_speed else 0.0,
            "peak_hour": peak,
            "peak_count": by_hour[peak] if peak is not None else 0,
            "daily_average": total / self.days_with_data(since, until),
            "occupancy": occupancy or 0.0,
        }

    def totals(self):
        """Devuelve los conteos acumulados del historial para que los contadores no arranquen en cero.

        total y by_class cuentan cada vehículo una sola vez (is_new); lines trae los cruces
        por línea y sentido: {línea: (sentido +, sentido -)}.
        """
        total = self._query("SELECT COUNT(*) FROM crossings WHERE is_new = 1")[0][0] or 0
        by_class = dict(self._query("SELECT cls, COUNT(*) FROM crossings WHERE is_new = 1 GROUP BY cls"))
        lines = {}
        for line, direction, count in self._query(
                "SELECT line, direction, COUNT(*) FROM crossings GROUP BY line, direction"):
            pos, neg = lines.get(line, (0, 0))
            lines[line] = (pos + count, neg) if direction > 0 else (pos, neg + count)
        return {"total": total, "by_class": by_class, "lines": lines}

    def recent_alarms(self, limit=50):
        """Devuelve las últimas alarmas registradas, de la más reciente a la más antigua."""
        return self._query(
            "SELECT ts_start, ts_end, code, severity, text FROM alarms ORDER BY ts_start DESC LIMIT ?", (limit,))

    # --- Exportación ---

    def export_csv(self, path, since, until):
        """Exporta los cruces del periodo a CSV (se abre directo en Excel) y devuelve cuantos son."""
        rows = self._query(
            "SELECT ts, line, direction, cls, speed FROM crossings WHERE ts BETWEEN ? AND ? ORDER BY ts",
            (since, until))
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["Fecha", "Hora", "Línea", "Sentido", "Tipo", "Velocidad (km/h)"])
            for ts, line, direction, cls_name, speed in rows:
                moment = datetime.fromtimestamp(ts)
                writer.writerow([moment.strftime("%d/%m/%Y"), moment.strftime("%H:%M:%S"), line,
                                   "+" if direction > 0 else "-", cls_name, f"{speed:.1f}".replace(".", ",")])
        return len(rows)
