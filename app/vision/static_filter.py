from .geometry import iou

IOU_SAME_REGION = 0.6
REGION_FORGET_S = 600          # regiones sin ver durante 10 min se descartan
MIN_MOTION = 0.02              # fracción de la diagonal del cuadro


class _Region:
    """Area del cuadro donde se acumula el tiempo que una caja permanece inmóvil."""

    __slots__ = ("box", "seconds", "last_time", "fixed")

    def __init__(self, box, now):
        """Crea la región a partir de una caja, sin tiempo acumulado."""
        self.box = list(box)
        self.seconds = 0.0
        self.last_time = now
        self.fixed = False


class FixedObjectFilter:
    """Oculta objetos fijos (letreros, vallas o postes) que YOLO confunde con vehículos.

    Un vehículo real llega a la escena moviéndose; un letrero aparece siempre en el
    mismo lugar y nunca se desplaza. Cada caja inmóvil desde que apareció acumula
    tiempo en una región; cuando una región suma fixed_object_s se marca como fija
    y las detecciones inmoviles sobre ella se ocultan (no se dibujan ni cuentan en
    escena ni en la cola). Un vehículo detenido en la cola del semáforo no se oculta
    porque llegó moviéndose, y lo que se mueve sobre una región fija se muestra normal.
    Parámetros: vision.conf [zone] hide_fixed_objects y fixed_object_s.
    """

    def __init__(self, active=True, fixed_time_s=45.0):
        """Prepara el filtro con su estado y el tiempo para considerar fija una región."""
        self.active = active
        self.fixed_time_s = fixed_time_s
        self.regions = []

    def configure(self, active, fixed_time_s):
        """Aplica nuevos parámetros (mínimo 5 s) y borra las regiones si se desactiva."""
        self.active = bool(active)
        self.fixed_time_s = max(5.0, float(fixed_time_s))
        if not self.active:
            self.regions = []

    def reset(self):
        """Borra todas las regiones acumuladas."""
        self.regions = []

    @property
    def fixed_count(self):
        """Devuelve cuantas regiones están marcadas como fijas."""
        return sum(1 for r in self.regions if r.fixed)

    @staticmethod
    def still(vehicle, diagonal):
        """Indica si el vehículo no se ha desplazado desde que apareció."""
        return vehicle.max_travel < MIN_MOTION * diagonal

    def _region_for(self, box):
        """Devuelve la región que más se solapa con la caja, o None si ninguna llega al umbral."""
        best, value = None, IOU_SAME_REGION
        for region in self.regions:
            v = iou(box, region.box)
            if v >= value:
                best, value = region, v
        return best

    def update_state(self, vehicles, dt, now, diagonal):
        """Acumula tiempo de las cajas inmoviles y marca cuales se ocultan."""
        for v in vehicles:
            v.hidden = False
        if not self.active:
            return
        # Solo cuentan los vehículos vistos en este cuadro y que no se han movido
        for v in vehicles:
            if now - v.last_seen > 0.05 or not self.still(v, diagonal):
                continue
            region = self._region_for(v.bbox)
            if region is None:
                region = _Region(v.bbox, now)
                self.regions.append(region)
            else:  # la región sigue la caja con suavidad
                region.box = [0.9 * r + 0.1 * c for r, c in zip(region.box, v.bbox)]
            region.seconds += dt
            region.last_time = now
            if region.seconds >= self.fixed_time_s:
                region.fixed = True
            v.hidden = region.fixed
        self.regions = [r for r in self.regions if now - r.last_time < REGION_FORGET_S]
