# LOGO! Traffic HMI

**Versión 1.0.0** · Desarrollado por [Juan Carabantes](https://github.com/Juan-Carabantes)

HMI de escritorio para supervisar y controlar un semáforo programado en un **Siemens LOGO!**, con **visión artificial** (YOLO) que cuenta vehículos, estima la velocidad y sugiere los tiempos de cada fase según la demanda.

## Funciones

- Semáforo en vivo, entradas/salidas digitales con cronómetro y registro de eventos.
- Control remoto por Ethernet S7: Marcha (M1), Paro (M2) y Cruce peatonal (M3).
- Reconexión automática si se pierde el enlace con el LOGO!.
- Detección y seguimiento con YOLO26 acelerado con OpenVINO (~3× más rápido en CPU) y hasta 4 líneas de conteo con sentido, ajustables con el ratón.
- Video fluido: captura, IA y pantalla trabajan en hilos separados; las cajas se dibujan en su posición prevista entre análisis.
- Confianza mínima por tipo de vehículo (motos incluidas), zona de detección dibujable y filtro de objetos fijos (letreros).
- Datos en vivo cada segundo: indicadores de la cámara, estadísticas y gráficas.
- Velocidad por vehículo actualizada cada 1 s (mediana), con calibración automática por perspectiva o manual con 2 clics.
- Video con fecha, hora, fuente, FPS, modelo y conteos. Sin cámara se muestra un botón para configurarla.
- Historial en SQLite: horas pico, tendencia, mapa de calor semanal, composición por tipo; exportación CSV y PDF.
- Alarmas (enlace PLC, congestión, cola, sin video) con campana en la barra superior.
- Tiempos recomendados para B3, B21, B6, B13 y B11 según el tráfico, **solo informativos**: la app no cambia tiempos en el LOGO!.
- B16 (señal intermitente) la define el usuario (5 s por defecto), sin sugerencia.
- Grabación del video procesado a MP4.
- Tema oscuro/claro, estilos en CSS y recarga en caliente con **F5**.

## Instalación

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Pruebas automáticas (opcional):

```powershell
pip install pytest
python -m pytest -q tests
```

## Estructura

```
LOGO-Traffic-HMI/
├── main.py                 Punto de entrada
├── tests/                  Pruebas automáticas (pytest)
├── app/
│   ├── config/             Configuración editable (.conf)
│   ├── core/               Configuración, rutas, registro, utilidades (sin interfaz)
│   ├── plc/                Comunicación S7 y controlador del LOGO!
│   ├── vision/             Captura, detección, seguimiento, dibujo y grabación
│   ├── analytics/          Análisis de tráfico, historial y tiempos recomendados
│   ├── assets/icons/       Iconos SVG (stroke="currentColor")
│   └── ui/
│       ├── window.py       Ventana principal (solo conecta módulos)
│       ├── navigation/     Barra lateral y barra superior
│       ├── views/          Páginas: Semáforo, Cámara, Estadísticas, Recomendaciones, Configuración
│       ├── dialogs/        Ventanas emergentes
│       ├── components/     Bloques reutilizables: Card, StatCard, StatusChip, iconos
│       ├── widgets/        Semáforo, tarjetas de E/S y superficie de video
│       └── styles/         Hojas .css modulares + cargador del tema
├── models/                 Modelos YOLO y versiones OpenVINO (se crea sola)
├── data/                   Base de datos (se crea sola)
├── logs/                   Bitácora de cada sesión (se crea sola)
└── recordings/             Videos grabados (se crea sola)
```

## Configuración (`app/config/`)

| Archivo | Contenido |
|---|---|
| `app.conf` | Archivo maestro: nombre, rutas, registro y lista de módulos |
| `plc.conf` | IP, TSAP, rack/slot, sondeo, reconexión, mapa de memoria VM, bits de control |
| `io.conf` | Entradas y salidas que se muestran en el HMI (nombre, bit, color) |
| `timers.conf` | Temporizadores del LOGO! (tiempo programado y `vw_read` para leerlo) |
| `camera.conf` | Fuente de video, resolución, grabación, reintento sin señal y datos en pantalla |
| `vision.conf` | Detección (motor, confianza por tipo), seguidor, zona, líneas de conteo, calibración y perfiles |
| `analytics.conf` | Reglas de tiempos recomendados, historial y alarmas |
| `ui.conf` | Ventana, escala de la interfaz, tamaños de letra, barra lateral, tema y orden de carga de los `.css` |
| `theme.conf` | Paletas de color (oscuro/claro), señales y tipografía |

La carpeta `app/config/defaults/` guarda los valores de fábrica: el botón **Restablecer** de cada área en Configuración los usa para volver solo esa área a su estado original.

Los valores se leen como `clave = valor`, sin comillas. La app guarda sus cambios modificando solo la línea afectada, así que los comentarios se conservan.

## Estilos (`app/ui/styles/`)

Cada bloque visual tiene su propia hoja `.css`. Los colores se toman de `theme.conf` con `var(--clave)`:

```css
QFrame#card {
    background-color: var(--area);
    border: 1px solid var(--border);
}
```

Desde Python no se usa `setStyleSheet()`: los widgets reciben un `objectName` o una propiedad (`variant`, `state`, `tone`…) y el CSS los selecciona.

## Mapa de memoria del LOGO!

| Área | Dirección S7 | Uso |
|---|---|---|
| Entradas I1–I8 | DB1.DBB1024 | Lectura |
| Salidas Q1–Q8 | DB1.DBB1064 | Lectura |
| Marcas M1–M8 | DB1.DBB1104 | Pulsos de control |

Se configuran en `app/config/plc.conf`.

## Crear el .exe

Doble clic en `build.bat` (usa el `venv` del proyecto). La primera vez tarda 10-20 minutos:

1. Instala PyInstaller.
2. Prepara los modelos YOLO26 y sus versiones OpenVINO en `models/` (así el .exe funciona sin internet).
3. Crea `dist\LOGO-Traffic-HMI.exe`: un solo archivo que no necesita Python ni nada más instalado.

El .exe guarda la configuración, el historial, los registros y las grabaciones en
`Documentos\LOGO Traffic HMI\`. La primera vez copia ahí la configuración incluida.

## Convenciones del código

- Nombres de archivos, carpetas, funciones, variables, claves `.conf` y tablas SQLite en inglés.
- Comentarios y textos de la interfaz en español.

## Control de versiones (Git)

```powershell
git status                      # ver que archivos cambiaron
git add .                       # preparar los cambios
git commit -m "Descripción del cambio"
git tag v1.1.0                  # marcar una versión nueva (opcional)
git log --oneline               # historial de cambios
```

`venv/`, `data/`, `logs/`, `recordings/`, `models/` y los modelos `*.pt` no se suben al repositorio (ver `.gitignore`).

