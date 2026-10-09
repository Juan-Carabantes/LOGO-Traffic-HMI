from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

from ...core.app_config import AppConfig
from ...core.settings import ICON_PATH
from ..components import icons
from ..scale import px, tx

# Páginas de la navegación (icono, texto); la última se coloca abajo, separada del resto
PAGES = (
    ("nav_hmi", "Semáforo"),
    ("nav_camera", "Cámara"),
    ("nav_analytics", "Estadísticas"),
    ("nav_timer", "Recomendaciones"),
    ("nav_settings", "Configuración"),
)


class NavButton(QPushButton):
    """Boton de la barra lateral con icono que cambia de color al estar seleccionado."""

    def __init__(self, icon, text, checkable=True, height=42, icon_size=20, parent=None):
        """Crea el botón con su icono, texto y tamaños, y lo registra para refrescar el icono."""
        super().__init__(parent)
        self.icon_name = icon
        self.label_text = text
        self.icon_size = icon_size
        self.setObjectName("navButton")
        self.setCheckable(checkable)
        self.setMinimumHeight(tx(height))   # crece si se agranda la letra
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setIconSize(QSize(tx(icon_size), tx(icon_size)))
        self.refresh_icon()
        icons.record(self, self.refresh_icon)
        self.set_collapsed(False)

    def refresh_icon(self):
        """Vuelve a generar el icono con los colores de la paleta actual."""
        self.setIcon(icons.state_icon(self.icon_name, "soft_text", "accent", self.icon_size))

    def set_collapsed(self, collapsed):
        """Oculta el texto cuando la barra esta colapsada y actualiza la propiedad collapsed."""
        self.setText("" if collapsed else f"   {self.label_text}")
        self.setProperty("collapsed", collapsed)


class CollapsibleSidebar(QFrame):
    """Barra lateral con marca, navegación con iconos y botón para colapsar.

    Estilos en app/ui/styles/layout/sidebar.css; tamaños en ui.conf, sección [sidebar].
    """

    page_changed = pyqtSignal(int)   # índice de la página elegida

    def __init__(self, parent=None):
        """Crea la marca, los botones de navegación y restaura el estado guardado."""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.cfg = AppConfig.get_instance()
        conf = self.cfg.section("ui", "sidebar")
        self.expanded_width = tx(conf.get("expanded_width", 232))
        self.collapsed_width = tx(conf.get("collapsed_width", 68))
        height = conf.get("button_height", 42)
        size = conf.get("icon_size", 20)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(12), px(14), px(12), px(14))
        layout.setSpacing(px(4))

        # Marca: logotipo, nombre y subtitulo
        marker = QHBoxLayout()
        marker.setSpacing(px(10))
        self.logo = QLabel()
        self.logo.setObjectName("sidebarLogo")
        self.logo.setFixedSize(tx(34), tx(34))
        if ICON_PATH.exists():
            pix = QPixmap(str(ICON_PATH))
            self.logo.setPixmap(pix.scaled(tx(34), tx(34), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        marker.addWidget(self.logo)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.lbl_name = QLabel("LOGO! Traffic")
        self.lbl_name.setObjectName("sidebarName")
        self.lbl_sub = QLabel("HMI · Visión artificial")
        self.lbl_sub.setObjectName("sidebarSub")
        texts.addWidget(self.lbl_name)
        texts.addWidget(self.lbl_sub)
        marker.addLayout(texts, stretch=1)
        layout.addLayout(marker)
        layout.addSpacing(px(18))

        # Botones de las páginas principales
        self.lbl_section = QLabel("NAVEGACIÓN")
        self.lbl_section.setObjectName("sidebarSection")
        layout.addWidget(self.lbl_section)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = []
        for index, (icon, text) in enumerate(PAGES[:-1]):
            button = NavButton(icon, text, True, height, size)
            self.group.addButton(button, index)
            self.buttons.append(button)
            layout.addWidget(button)
        self.buttons[0].setChecked(True)

        layout.addStretch(1)

        # Configuración y botón de colapsar al pie de la barra
        icon, text = PAGES[-1]
        self.btn_config = NavButton(icon, text, True, height, size)
        self.group.addButton(self.btn_config, len(PAGES) - 1)
        self.buttons.append(self.btn_config)
        layout.addWidget(self.btn_config)

        self.btn_collapse = NavButton("nav_menu", "Contraer menú", False, height, size)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        layout.addWidget(self.btn_collapse)

        # Estado inicial según sidebar_expanded de ui.conf
        self.group.idClicked.connect(self.page_changed.emit)
        self.is_collapsed = False
        self.set_collapsed(not conf.get("sidebar_expanded", True), save=False)

    def set_active_page(self, index):
        """Marca como seleccionado el botón de la página indicada."""
        button = self.group.button(index)
        if button:
            button.setChecked(True)

    def toggle_collapse(self):
        """Alterna entre barra expandida y colapsada."""
        self.set_collapsed(not self.is_collapsed)

    def set_collapsed(self, collapsed, save=True):
        """Colapsa o expande la barra y, si save es True, guarda el estado en ui.conf."""
        self.is_collapsed = collapsed
        self.setFixedWidth(self.collapsed_width if collapsed else self.expanded_width)
        for widget in (self.lbl_name, self.lbl_sub, self.lbl_section):
            widget.setVisible(not collapsed)
        for button in self.buttons + [self.btn_collapse]:
            button.set_collapsed(collapsed)
        self.btn_collapse.label_text = "Expandir menú" if collapsed else "Contraer menú"
        self.btn_collapse.set_collapsed(collapsed)
        if save:
            self.cfg.set("ui", "sidebar_expanded", not collapsed)
