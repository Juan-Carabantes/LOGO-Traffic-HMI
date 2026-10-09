from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ...core.formatting import format_mm_ss
from ...core.hardware_detector import update_interval_ms
from ...core.timers_map import load_timer_blocks
from ..components import Card, PageHeader, ResponsiveGrid, StatCard, StatusChip
from ..scale import px


def _text(text, name, wrap=False):
    """Crea una etiqueta con su nombre de objeto para el CSS."""
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def interval_text(ms):
    """Describe el intervalo de actualización para mostrarlo al usuario."""
    if ms < 1000:
        return "Tiempo real"
    seconds = ms / 1000.0
    return f"Cada {seconds:.0f} s" if seconds.is_integer() else f"Cada {seconds:.1f} s"


# --- Tarjeta de un temporizador ---

class _TimerCard(QFrame):
    """Tarjeta de un bloque temporizador: tiempo recomendado y motivo."""

    def __init__(self, block, parent=None):
        """Crea la tarjeta del bloque sin recomendación hasta que llegue el tráfico."""
        super().__init__(parent)
        self.setObjectName("timerCard")
        self.block = block
        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(16), px(14), px(16), px(14))
        layout.setSpacing(px(10))

        # Encabezado: identificador del bloque, nombre y salida
        header = QHBoxLayout()
        header.setSpacing(px(10))
        header.addWidget(_text(block.id, "timerBadge"), alignment=Qt.AlignmentFlag.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(px(1))
        names.addWidget(_text(block.name, "timerName", wrap=True))
        if block.output:
            names.addWidget(_text(f"Salida {block.output}", "timerOutput"))
        header.addLayout(names, stretch=1)
        layout.addLayout(header)

        # Tiempo recomendado
        values = QHBoxLayout()
        self.lbl_suggested, self.lbl_rule = self._value_box(values, "Recomendado", "suggested")
        layout.addLayout(values)

        # Motivo de la recomendación
        self.lbl_reason = _text(block.reason, "timerReason", wrap=True)
        layout.addWidget(self.lbl_reason)
        layout.addStretch(1)
        self.lbl_suggested.setText("—")
        self.lbl_rule.setText("Esperando tráfico")

    def _value_box(self, parent_layout, title, kind):
        """Agrega un recuadro con título, valor grande y detalle; devuelve (valor, detalle)."""
        box = QFrame()
        box.setObjectName("timerValueBox")
        box.setProperty("kind", kind)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(px(12), px(8), px(12), px(8))
        inner.setSpacing(px(1))
        inner.addWidget(_text(title.upper(), "timerValueTitle"))
        value = _text("—", "timerValue")
        inner.addWidget(value)
        detail = _text("", "timerValueDetail", wrap=True)
        inner.addWidget(detail)
        parent_layout.addWidget(box, stretch=1)
        return value, detail

    def show_suggestion(self, seconds, reason, fixed=False):
        """Muestra el tiempo recomendado y el motivo."""
        self.lbl_suggested.setText(format_mm_ss(seconds))
        self.lbl_rule.setText("Valor fijo (analytics.conf)" if fixed else "Según el tráfico en vivo")
        self.lbl_reason.setText(reason or self.block.reason)


# --- Página de recomendaciones ---

class RecommendationsView(QWidget):
    """Página de tiempos recomendados para cada temporizador del Logo, calculados en vivo.

    Solo es informativa: el Logo no permite cambiar los tiempos desde la app. Se actualiza
    con cada envío de estadísticas del video (intervalo de analytics.conf update_interval).
    Estilos en app/ui/styles/views/recommendations_view.css.
    """

    def __init__(self, parent=None):
        """Arma el encabezado, los indicadores del tráfico y una tarjeta por temporizador."""
        super().__init__(parent)
        self.blocks = {b.id: b for b in load_timer_blocks(only_analytics=True)}
        self.suggested = {}

        # Contenido dentro de un área con desplazamiento vertical
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("pageScroll")
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(px(24), px(20), px(24), px(24))
        root.setSpacing(px(16))

        # Encabezado con la frecuencia y la hora de la última actualización
        header = PageHeader("Tiempos recomendados",
                            "Calculados con el tráfico en vivo · solo informativo, el LOGO! no permite "
                            "cambiar los tiempos desde la app")
        self.chip_interval = StatusChip("Actualización", interval_text(update_interval_ms()), "info")
        self.chip_updated = StatusChip("Última", "—", "neutral")
        header.add_action(self.chip_interval)
        header.add_action(self.chip_updated)
        root.addWidget(header)

        # Indicadores del tráfico que usan las reglas
        self.kpi_flow = StatCard("Caudal actual", "status_activity", "success", "veh/min", compact=True)
        self.kpi_scene = StatCard("En escena", "status_counter", "accent", "veh", compact=True)
        self.kpi_speed = StatCard("Velocidad media", "status_gauge", "warning", "km/h", compact=True)
        self.kpi_cycle = StatCard("Ciclo sugerido", "nav_timer", "text", "min", compact=True)
        root.addWidget(ResponsiveGrid((self.kpi_flow, self.kpi_scene, self.kpi_speed, self.kpi_cycle),
                                      spacing=10))

        # Una tarjeta por temporizador (hasta 3 columnas)
        self.cards = {}
        grid = ResponsiveGrid(max_columns=3, spacing=16)
        for block in self.blocks.values():
            card = _TimerCard(block)
            self.cards[block.id] = card
            grid.add_widget(card)
        root.addWidget(grid)

        # Nota sobre el origen de los tiempos recomendados
        note = Card("Cómo se obtienen", "Tiempo recomendado")
        note.body.addWidget(_text(
            "Calculado con el tráfico de los últimos minutos según las reglas de app/config/analytics.conf, "
            "por si quieres reprogramar el LOGO! en LOGO!Soft. Los parpadeos (B11 y B16) son valores fijos.",
            "helpText", wrap=True))
        root.addWidget(note)
        root.addStretch(1)

    # --- Datos en vivo ---

    def set_interval(self, ms):
        """Muestra la frecuencia de actualización vigente."""
        self.chip_interval.set_state("info", interval_text(ms))

    def update_stats(self, stats):
        """Actualiza indicadores y recomendaciones con las estadísticas del video."""
        self.kpi_flow.set_value(f"{stats.get('flow_min', 0):.0f}", f"≈ {stats.get('flow_hour', 0):.0f} veh/h")
        self.kpi_scene.set_value(stats.get("vehicles_in_scene", 0), f"{stats.get('stopped', 0)} detenidos")
        self.kpi_speed.set_value(f"{stats.get('avg_speed', 0):.1f}",
                                 f"Ocupación {stats.get('density_pct', 0):.0f} %")
        for block_id, data in stats.get("timer_suggestions", {}).items():
            if block_id in self.cards:
                self.suggested[block_id] = (float(data.get("seconds", 0)), data.get("reason", ""),
                                            bool(data.get("fixed", False)))
                self._show_suggestion(block_id)
        # Ciclo completo sugerido: verde + amarillo + rojo sin espera
        cycle = sum(self.suggested[b][0] for b in ("B3", "B21", "B6") if b in self.suggested)
        self.kpi_cycle.set_value(format_mm_ss(cycle), "Verde + amarillo + rojo")
        self.chip_updated.set_state("success", datetime.now().strftime("%H:%M:%S"))

    def _show_suggestion(self, block_id):
        """Pinta la recomendación del bloque si ya existe."""
        if block_id in self.suggested:
            seconds, reason, fixed = self.suggested[block_id]
            self.cards[block_id].show_suggestion(seconds, reason, fixed)

    def report_rows(self):
        """Filas para el informe PDF: bloque, función y tiempo recomendado."""
        rows = []
        for block_id, block in self.blocks.items():
            suggested = format_mm_ss(self.suggested[block_id][0]) if block_id in self.suggested else "—"
            rows.append([block_id, block.function, suggested])
        return rows
