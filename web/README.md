# Web del proyecto LOGO! Traffic HMI

Página de presentación del semáforo con Siemens LOGO!. Para verla en la PC: doble clic en `index.html`.

## Estructura

```
web/
├── index.html        Textos y secciones de la página
├── css/estilos.css   Diseño y colores
├── js/app.js         Menú, visor de imágenes y recuadros de imágenes faltantes
├── js/iconos.js      Iconos SVG (mismo estilo que la app)
└── img/              Imágenes de la página
```

## Imágenes que se deben colocar en `img/`

| Archivo | Dónde aparece |
|---|---|
| `portada.jpg` | Foto principal de la portada (mientras no exista se muestra un semáforo animado) |
| `diagrama_electrico.png` | Diagramas → Diagrama eléctrico |
| `maqueta_1.jpg` … `maqueta_4.jpg` | Fotos de la maqueta: vista general, tablero de control, semáforo, botonera y pilotos |
| `integrante_1.jpg` … `integrante_4.jpg` | Foto de cada integrante (sección Equipo); cuadrada, se recorta en círculo |
| `equipo_grupo.jpg` | Foto grupal destacada de la galería; horizontal 16:9 |
| `equipo_4.jpg` … `equipo_12.jpg` | Galería (sección Equipo): verticales 3:4; `equipo_8` y `equipo_9` horizontales 4:3 (ocupan 2 columnas) |

Las capturas `app_semaforo.png`, `app_camara.jpg`, `app_estadisticas.png`, `app_recomendaciones.png` y `app_configuracion.png` ya están incluidas, igual que `programa_logo.png` (diagrama del Tablero Principal) y `logo_itcha.svg` (logo del instituto, en Equipo y Créditos).

El diagrama de bloques (`dibujarBloques`) y el de comunicación ya están dibujados en la página (`js/app.js`, funciones `dibujarBloques` y `dibujarRed`).

El video demostrativo está en YouTube (https://youtu.be/yE7l-pta1g4) y se muestra en la sección Maqueta; para cambiarlo se edita el `<iframe>` en `index.html`.

Mientras una imagen no exista, la página muestra un recuadro con el nombre que debe tener.
Los nombres deben coincidir exactamente (minúsculas y extensión .jpg o .png).

## Cambiar textos

Todos los textos están en `index.html`. Cada sección empieza con un comentario `<!-- --- Nombre --- -->`.

## Publicar en GitHub Pages

La página se publica sola con GitHub Actions (`.github/workflows/pages.yml`) cada vez que se sube un cambio en `web/` a la rama `main`.

Configuración (solo la primera vez): en el repositorio, **Settings → Pages → Source: GitHub Actions**.

Queda en: `https://juan-carabantes.github.io/LOGO-Traffic-HMI/`
