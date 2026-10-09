import time

from app.analytics.history import HistoryStore
from app.analytics.traffic_analyzer import TrafficAnalyzer
from app.core.alarms import AlarmManager


def test_suggestions_and_blink():
    """Comprueba el verde sugerido con congestion lenta y los tiempos fijos de parpadeo."""
    suggestions = TrafficAnalyzer().calculate_suggested_timers(4, 10.0)
    assert suggestions["B3"]["seconds"] == 60   # level_3 (45 s) + congestion lenta (+15)
    assert suggestions["B11"]["seconds"] == 3 and suggestions["B16"]["seconds"] == 5


def test_alarm_delay():
    """Comprueba que la alarma solo se activa tras el retardo y se desactiva al cesar la condición."""
    alarms = AlarmManager()
    events = []
    alarms.subscribe(lambda evt, alarm: events.append(evt))
    alarms.evaluate("queue", True, "Cola", delay_s=30, now=100)
    assert not alarms.active
    alarms.evaluate("queue", True, "Cola", delay_s=30, now=131)
    assert "queue" in alarms.active
    alarms.evaluate("queue", False, "Cola")
    assert events == ["activated", "deactivated"]


def test_history_peak_hours(tmp_path):
    """Comprueba el total, la hora pico y el conteo por clase del historial."""
    history = HistoryStore(tmp_path / "h.sqlite3")
    base = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    # 30 autos a las 17 h y 10 camiones a las 8 h del día actual
    events = [{"timestamp": base + 17 * 3600 + i, "class": "car"} for i in range(30)]
    events += [{"timestamp": base + 8 * 3600 + i, "class": "truck"} for i in range(10)]
    history.record_crossings(events)
    history.flush()
    summary = history.summary(base, base + 86400)
    assert summary["total"] == 40
    assert summary["peak_hour"] == 17
    assert history.by_class(base, base + 86400) == {"car": 30, "truck": 10}
    history.close()
