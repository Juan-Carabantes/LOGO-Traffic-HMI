from datetime import datetime

from PyQt6.QtCore import QMarginsF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter


def export_pdf(path, title, subtitle, kpis, charts, table=None):
    """Genera el informe PDF de estadísticas con QPdfWriter, sin librerias extra.

    kpis: [(etiqueta, valor)], charts: [(título, QWidget)], table: (cabeceras, filas).
    """
    # Página A4 vertical con margenes de 14 mm
    pdf = QPdfWriter(str(path))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter))
    pdf.setResolution(150)
    pdf.setTitle(title)

    p = QPainter(pdf)
    width = pdf.width()
    page_height = pdf.height()
    ink, smooth, line = QColor("#111827"), QColor("#5b6677"), QColor("#e3e8ef")

    def source(size, bold=False):
        """Asigna al pintor la fuente Segoe UI con el tamaño y el grosor indicados."""
        f = QFont("Segoe UI")
        f.setPointSizeF(size)
        f.setBold(bold)
        p.setFont(f)

    # Título y subtitulo con la fecha de generación
    y = 0
    source(18, True)
    p.setPen(ink)
    p.drawText(QRectF(0, y, width, 60), Qt.AlignmentFlag.AlignLeft, title)
    y += 60
    source(9)
    p.setPen(smooth)
    p.drawText(QRectF(0, y, width, 30), Qt.AlignmentFlag.AlignLeft,
               f"{subtitle}  ·  Generado el {datetime.now():%d/%m/%Y %H:%M}")
    y += 50

    # Indicadores en una fila de recuadros
    if kpis:
        box = width / len(kpis)
        for i, (label, value) in enumerate(kpis):
            x = i * box
            p.setPen(line)
            p.drawRoundedRect(QRectF(x + 4, y, box - 8, 110), 10, 10)
            source(8)
            p.setPen(smooth)
            p.drawText(QRectF(x + 20, y + 12, box - 40, 26), Qt.AlignmentFlag.AlignLeft, label)
            source(16, True)
            p.setPen(ink)
            p.drawText(QRectF(x + 20, y + 42, box - 40, 50), Qt.AlignmentFlag.AlignLeft, str(value))
        y += 140

    # Gráficas: captura de cada widget tal como se ve, con salto de página si no cabe
    for chart_title, widget in charts:
        image = widget.grab()
        if image.isNull():
            continue
        height = width * image.height() / max(1, image.width())
        if y + height + 50 > page_height:
            pdf.newPage()
            y = 0
        source(11, True)
        p.setPen(ink)
        p.drawText(QRectF(0, y, width, 34), Qt.AlignmentFlag.AlignLeft, chart_title)
        y += 40
        p.drawPixmap(QRectF(0, y, width, height).toRect(), image)
        y += height + 30

    # Tabla: cabeceras y filas separadas por líneas
    if table:
        headers, rows = table
        row_height = 34
        if y + row_height * (len(rows) + 2) > page_height:
            pdf.newPage()
            y = 0
        col = width / len(headers)
        source(8.5, True)
        p.setPen(smooth)
        for i, head in enumerate(headers):
            p.drawText(QRectF(i * col, y, col, row_height), Qt.AlignmentFlag.AlignVCenter, head)
        y += row_height
        source(9)
        for row in rows:
            p.setPen(line)
            p.drawLine(0, int(y), int(width), int(y))
            p.setPen(ink)
            for i, value in enumerate(row):
                p.drawText(QRectF(i * col, y, col, row_height), Qt.AlignmentFlag.AlignVCenter, str(value))
            y += row_height
    p.end()
