from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..styles.theme import color
from ..scale import px


class TrafficLightWidget(QWidget):
    """Semáforo dibujado a mano que se adapta al espacio disponible.

    Colores en theme.conf, sección [Traffic_light].
    """

    RATIO = 2.75  # alto / ancho de la caja

    def __init__(self, parent=None):
        """Crea el semáforo con las tres luces apagadas."""
        super().__init__(parent)
        self.green_on = self.yellow_on = self.red_on = False
        self.setMinimumSize(px(120), px(300))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_lights(self, green, yellow, red):
        """Enciende o apaga las luces y repinta solo si algo cambio."""
        states = (bool(green), bool(yellow), bool(red))
        if states != (self.green_on, self.yellow_on, self.red_on):
            self.green_on, self.yellow_on, self.red_on = states
            self.update()

    def paintEvent(self, event):
        """Dibuja el poste, la carcasa y las tres luces con halo en las encendidas."""
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Tamaño de la caja y del poste según el espacio disponible (ancho máximo 200 px)
        margin = 16
        avail_height = self.height() - 2 * margin
        avail_width = self.width() - 2 * margin
        box_width = min(avail_width, avail_height / (self.RATIO + 0.35), 200)
        box_height = box_width * self.RATIO
        pole_height = min(box_width * 0.35, max(0.0, avail_height - box_height))
        x = (self.width() - box_width) / 2
        y = margin + (avail_height - box_height - pole_height) / 2

        # Poste
        pole_width = box_width * 0.16
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color("traffic_light_pole", "#2b313d"))
        p.drawRoundedRect(QRectF(x + (box_width - pole_width) / 2, y + box_height - 4, pole_width, pole_height + 4), 3, 3)

        # Carcasa con degradado vertical
        box = QRectF(x, y, box_width, box_height)
        radius = box_width * 0.22
        housing = color("traffic_light_housing", "#15181e")
        grad = QLinearGradient(box.topLeft(), box.bottomLeft())
        grad.setColorAt(0.0, housing.lighter(135))
        grad.setColorAt(1.0, housing)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(color("traffic_light_frame", "#2f3644"), max(2.0, box_width * 0.02)))
        p.drawRoundedRect(box, radius, radius)

        # Luces de arriba hacia abajo: rojo, amarillo y verde
        lens_r = box_width * 0.30
        center_x = x + box_width / 2
        step = box_height / 3
        lights = (
            (self.red_on, "red"),
            (self.yellow_on, "yellow"),
            (self.green_on, "green"),
        )
        viewer = color("traffic_light_visor", "#0a0c10")
        lens_border = color("traffic_light_lens_border", "#050608")
        for index, (lit, name) in enumerate(lights):
            cy = y + step * index + step / 2
            on = color(f"traffic_light_{name}_on", "#ffffff")
            off = color(f"traffic_light_{name}_off", "#222222")

            # Visera
            visor = QPainterPath()
            visor.addEllipse(QRectF(center_x - lens_r * 1.18, cy - lens_r * 1.22, lens_r * 2.36, lens_r * 2.36))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(viewer)
            p.drawPath(visor)

            # Encendida: halo radial y lente con brillo; apagada: lente oscura
            if lit:
                halo = QRadialGradient(center_x, cy, lens_r * 1.9)
                for pos, alpha in ((0.0, 170), (0.55, 55), (1.0, 0)):
                    c = QColor(on)
                    c.setAlpha(alpha)
                    halo.setColorAt(pos, c)
                p.setBrush(QBrush(halo))
                p.drawEllipse(QRectF(center_x - lens_r * 1.9, cy - lens_r * 1.9, lens_r * 3.8, lens_r * 3.8))

                lens = QRadialGradient(center_x - lens_r * 0.3, cy - lens_r * 0.3, lens_r * 1.2)
                lens.setColorAt(0.0, QColor(255, 255, 255))
                lens.setColorAt(0.25, on.lighter(115))
                lens.setColorAt(0.8, on)
                lens.setColorAt(1.0, on.darker(170))
            else:
                lens = QRadialGradient(center_x - lens_r * 0.35, cy - lens_r * 0.35, lens_r * 1.2)
                lens.setColorAt(0.0, off.lighter(150))
                lens.setColorAt(0.85, off)
                lens.setColorAt(1.0, off.darker(160))

            # Lente con borde
            p.setPen(QPen(lens_border, 2))
            p.setBrush(QBrush(lens))
            p.drawEllipse(QRectF(center_x - lens_r, cy - lens_r, lens_r * 2, lens_r * 2))
        p.end()
