from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...analytics.history import WEEKDAYS, period_range
from ..components import AdaptiveRow, Card, PageHeader, ResponsiveGrid, StatCard, icons
from ..components.charts import BarChart, HeatmapChart, LineChart
from ..components.segmented import SegmentedControl
from ..reports import export_pdf
from ..scale import px, tx

# Periodos del selector y su texto largo para indicadores e informes
_PERIODS = (("today", "Hoy"), ("7d", "7 días"), ("30d", "30 días"))
_PERIOD_TEXT = {"today": "Hoy", "7d": "Últimos 7 días", "30d": "Últimos 30 días"}
# Tipos de vehículo: (clase de YOLO, nombre visible, icono)
_CLASSES = (
    ("car", "Automóviles", "vehicle_car"),
    ("motorcycle", "Motocicletas", "vehicle_motorcycle"),
    ("bus", "Autobuses", "vehicle_bus"),
    ("truck", "Camiones", "vehicle_truck"),
)


def _table(columns, fixed_rows=0):
    """Crea una tabla de solo lectura, sin selección ni cuadricula, con columnas ajustadas al ancho."""
    table = QTableWidget(fixed_rows, len(columns))
    table.setObjectName("dataTable")
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(tx(40))
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    header_view = table.horizontalHeader()
    header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header_view.setHighlightSections(False)
    header_view.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return table


def _note(text):
    """Crea una etiqueta de ayuda con ajuste de línea."""
    label = QLabel(text)
    label.setObjectName("helpText")
    label.setWordWrap(True)
    return label


def _cell(table, row, column, text):
    """Escribe el texto en la celda, creandola si todavía no existe."""
    item = table.item(row, column)
    if item is None:
        table.setItem(row, column, QTableWidgetItem(str(text)))
    else:
        item.setText(str(text))


class _ClassRow(QWidget):
    """Fila de un tipo de vehículo con su cantidad y una barra de proporción."""

    def __init__(self, name, icon, parent=None):
        """Arma la fila con icono, nombre, valor y barra; el icono se repinta al cambiar el tema."""
        super().__init__(parent)
        self._icon = icon
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(6))

        # Línea superior: icono, nombre y valor
        row = QHBoxLayout()
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(tx(20), tx(20))
        self._paint_icon()
        icons.record(self, self._paint_icon)
        row.addWidget(self.lbl_icon)
        label = QLabel(name)
        label.setObjectName("classLabel")
        row.addWidget(label, stretch=1)
        self.value = QLabel("0")
        self.value.setObjectName("classValue")
        row.addWidget(self.value)
        layout.addLayout(row)

        # Barra de proporción con resolución de 0.1 %
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(px(6))
        self.bar.setRange(0, 1000)
        layout.addWidget(self.bar)

    def _paint_icon(self):
        """Dibuja el icono del tipo de vehículo con el color actual del tema."""
        self.lbl_icon.setPixmap(icons.icon_pixmap(self._icon, "soft_text", 18))

    def set_value(self, count, fraction):
        """Muestra la cantidad y el porcentaje y ajusta la barra (fraction entre 0 y 1)."""
        self.value.setText(f"{count}  ·  {fraction * 100:.0f} %")
        self.bar.setValue(int(fraction * 1000))


class AnalyticsView(QWidget):
    """Página de estadísticas: historial, horas pico, tendencia, mapa de calor y cruces por línea.

    Los tiempos recomendados están en su propia página (recommendations_view.py); el PDF
    los toma de ahí con report_rows. Los datos historicos vienen de app/analytics/history.py (data/traffic_history.sqlite3)
    y los estilos están en app/ui/styles/views/analytics_view.css.
    """

    message = pyqtSignal(str)   # texto para el registro de eventos

    def __init__(self, history, parent=None):
        """Arma la página con desplazamiento, indicadores, gráficas y tablas, y carga el historial."""
        super().__init__(parent)
        self.history = history
        self.period = "7d"
        self.report_rows = lambda: []   # filas de tiempos para el PDF (las da la página Recomendaciones)

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

        root.addWidget(self._header())
        root.addWidget(self._kpis())

        # Fila 1: vehículos por hora y composición del tráfico (se apilan si no caben)
        row1 = AdaptiveRow(breakpoint=900)
        self.card_hours = Card("Vehículos por hora del día", "Promedio por día · las 3 horas pico resaltadas")
        self.hours_chart = BarChart("veh/h")
        self.card_hours.body.addWidget(self.hours_chart)
        row1.add(self.card_hours, stretch=3)
        row1.add(self._composition_card(), stretch=2)
        root.addWidget(row1)

        # Fila 2: tendencia y mapa de calor semanal (se apilan si no caben)
        row2 = AdaptiveRow(breakpoint=900)
        self.card_trend = Card("Tendencia", "Vehículos por día")
        self.trend_chart = LineChart("veh")
        self.card_trend.body.addWidget(self.trend_chart)
        row2.add(self.card_trend, stretch=1)
        card_heat = Card("Mapa de calor semanal", "Últimos 30 días · vehículos por hora según el día")
        self.heat_chart = HeatmapChart(WEEKDAYS, [f"{h:02d}" for h in range(24)])
        card_heat.body.addWidget(self.heat_chart)
        row2.add(card_heat, stretch=1)
        root.addWidget(row2)

        root.addWidget(self._lines_card())

        # La ventana principal llama a refresh_history() cada segundo mientras esta página se ve
        self.refresh_history()

    # --- Construcción ---

    def _header(self):
        """Crea el encabezado con el selector de periodo y los botones de exportar CSV y PDF."""
        header = PageHeader("Estadísticas de tráfico", "Historial, horas pico y demanda por hora")
        self.selector = SegmentedControl(_PERIODS, self.period)
        self.selector.changed.connect(self._change_period)
        header.add_action(self.selector)
        for text, icon, action in (("  CSV", "action_download", self._export_csv),
                                     ("  PDF", "action_file", self._export_pdf)):
            button = QPushButton(text)
            button.setProperty("variant", "secondary")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"Exportar {text.strip()} del periodo")
            button.clicked.connect(action)
            icons.apply(button, icon, "text", 16)
            header.add_action(button)
        return header

    def _kpis(self):
        """Crea los indicadores del periodo: una fila en pantallas anchas y más filas si no caben."""
        self.kpi_total = StatCard("Vehículos", "status_counter", "accent", "veh")
        self.kpi_peak = StatCard("Hora pico", "status_clock", "warning", "")
        self.kpi_daily = StatCard("Promedio diario", "status_trend", "success", "veh/día")
        self.kpi_speed = StatCard("Velocidad media", "status_gauge", "text", "km/h")
        return ResponsiveGrid((self.kpi_total, self.kpi_peak, self.kpi_daily, self.kpi_speed), spacing=12)

    def _composition_card(self):
        """Crea la tarjeta con la proporción de cada tipo de vehículo."""
        card = Card("Composición del tráfico", "Tipos de vehículo en el periodo")
        self.class_rows = {}
        for key, name, icon in _CLASSES:
            row = _ClassRow(name, icon)
            self.class_rows[key] = row
            card.body.addWidget(row)
        card.body.addStretch(1)
        return card

    def _lines_card(self):
        """Crea la tabla de cruces por línea de conteo y sentido."""
        card = Card("Líneas de conteo", "Cruces acumulados por sentido")
        self.lines_table = _table(["Línea", "Sentido +", "Sentido −", "Total"])
        self.lines_table.setMinimumHeight(tx(160))
        card.body.addWidget(self.lines_table)
        return card

    # --- Datos historicos ---

    def _change_period(self, period):
        """Cambia el periodo seleccionado y recarga el historial."""
        self.period = period
        self.refresh_history()

    def refresh_history(self):
        """Recalcula indicadores, gráficas y composición con el historial del periodo."""
        if self.history is None:
            return
        self.history.flush()
        since, until = period_range(self.period)
        summary = self.history.summary(since, until)

        # Indicadores del periodo
        self.kpi_total.set_value(f"{summary['total']:,}".replace(",", "."), _PERIOD_TEXT[self.period])
        if summary["peak_hour"] is not None:
            h = summary["peak_hour"]
            self.kpi_peak.set_value(f"{h:02d}:00",
                                    f"{h:02d}:00–{(h + 1) % 24:02d}:00 · ≈ {summary['peak_count']:.0f} veh/h")
        else:
            self.kpi_peak.set_value("—", "Sin datos todavía")
        self.kpi_daily.set_value(f"{summary['daily_average']:.0f}", "Días con datos en el periodo")
        self.kpi_speed.set_value(f"{summary['speed']:.1f}", f"Ocupación media {summary['occupancy']:.0f} %")

        # Vehículos por hora del día con las 3 horas pico resaltadas
        by_hour = self.history.by_hour_of_day(since, until)
        peak = sorted(range(24), key=lambda i: by_hour[i], reverse=True)[:3] if any(by_hour) else []
        self.hours_chart.set_data([f"{h:02d}" for h in range(24)], by_hour, peak, label_every=2)

        # Tendencia: por hora si el periodo es hoy, por día en los demás
        by = "hour" if self.period == "today" else "day"
        series = self.history.trend(since, until, by)
        self.card_trend.lbl_subtitle.setText("Vehículos por hora (hoy)" if by == "hour" else "Vehículos por día")
        self.trend_chart.set_data([e for e, _ in series], [v for _, v in series],
                                         label_every=3 if by == "hour" else max(1, len(series) // 8))

        # El mapa de calor siempre usa los últimos 30 días
        heat_since, _ = period_range("30d")
        self.heat_chart.set_data(self.history.heatmap(heat_since, until))

        # Composición por tipo de vehículo
        classes = self.history.by_class(since, until)
        total = sum(classes.values())
        for key, row in self.class_rows.items():
            count = classes.get(key, 0)
            row.set_value(count, count / total if total else 0.0)

    # --- Datos en vivo ---

    def update_stats(self, stats):
        """Actualiza la tabla de cruces por línea con las estadísticas en vivo."""
        # Cruces por línea de conteo
        lines = stats.get("count_by_line", [])
        self.lines_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            numbers = [f"{line[k]:,}".replace(",", ".") for k in ("pos", "neg", "total")]   # separador de miles
            for column, value in enumerate((line["name"], *numbers)):
                _cell(self.lines_table, row, column, value)

    # --- Exportación ---

    def _file_name(self, extension):
        """Devuelve el nombre sugerido del archivo con el periodo y la fecha actual."""
        return f"traffic_{self.period}_{datetime.now():%Y-%m-%d_%H%M}.{extension}"

    def _export_csv(self):
        """Pide una ruta y exporta a CSV los registros del periodo."""
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", self._file_name("csv"), "CSV (*.csv)")
        if path:
            since, until = period_range(self.period)
            rows = self.history.export_csv(path, since, until)
            self.message.emit(f"CSV exportado: {rows} registros en {path}")

    def _export_pdf(self):
        """Pide una ruta y guarda el informe PDF del periodo."""
        path, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", self._file_name("pdf"), "PDF (*.pdf)")
        if not path:
            return
        self.generate_pdf(path)
        self.message.emit(f"Informe PDF guardado en {path}")

    def generate_pdf(self, path):
        """Genera el informe PDF con los indicadores, las gráficas y la tabla de tiempos (sin la columna Motivo)."""
        kpis = [(k.lbl_label.text(), f"{k.lbl_value.text()} {k.lbl_unit.text()}".strip())
                       for k in (self.kpi_total, self.kpi_peak, self.kpi_daily, self.kpi_speed)]
        rows = self.report_rows()
        export_pdf(
            path, "Informe de tráfico — LOGO! Traffic HMI", _PERIOD_TEXT[self.period], kpis,
            [("Vehículos por hora del día", self.hours_chart),
             (self.card_trend.lbl_subtitle.text(), self.trend_chart),
             ("Mapa de calor semanal", self.heat_chart)],
            (["Bloque", "Función", "Recomendado"], rows),
        )
