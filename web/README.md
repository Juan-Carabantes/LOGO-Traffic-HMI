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
| `maqueta_1.jpg` … `maqueta_6.jpg` | Fotos de la maqueta |
| `demostracion.mp4` | Video demostrativo (sección Maqueta) |
| `equipo.jpg` | Foto del equipo (sección Equipo) |

Las capturas `app_semaforo.png`, `app_camara.jpg`, `app_estadisticas.png`, `app_recomendaciones.png` y `app_configuracion.png` ya están incluidas, igual que `programa_logo.png` (diagrama del Tablero Principal).

El diagrama de bloques (`dibujarBloques`) y el de comunicación ya están dibujados en la página (`js/app.js`, funciones `dibujarBloques` y `dibujarRed`).

Mientras una imagen no exista, la página muestra un recuadro con el nombre que debe tener.
Los nombres deben coincidir exactamente (minúsculas y extensión .jpg o .png).

## Cambiar textos

Todos los textos están en `index.html`. Cada sección empieza con un comentario `<!-- --- Nombre --- -->`.

## Publicar en GitHub Pages

1. En GitHub: **New repository** → nombre `logo-traffic-hmi-web` → **Public** → **Create repository**.
2. **uploading an existing file** → arrastrar el contenido de esta carpeta `web` (no la carpeta) → **Commit changes**.
3. **Settings → Pages → Source: Deploy from a branch → Branch: main / (root) → Save**.
4. En 1 o 2 minutos queda en: `https://juan-carabantes.github.io/logo-traffic-hmi-web/`
