// --- Iconos de la página ---
pintarIconos();


// --- Menú en celulares: abre y cierra la lista de enlaces ---
const navEnlaces = document.getElementById("navEnlaces");
document.getElementById("navBoton").addEventListener("click", () => navEnlaces.classList.toggle("abierto"));
navEnlaces.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => navEnlaces.classList.remove("abierto")));


// --- Marca en el menú la sección que se esta viendo ---
const secciones = document.querySelectorAll("section[id]");
const observador = new IntersectionObserver((entradas) => {
  entradas.forEach((e) => {
    if (!e.isIntersecting) return;
    navEnlaces.querySelectorAll("a").forEach((a) => a.classList.toggle("activo", a.getAttribute("href") === "#" + e.target.id));
  });
}, { rootMargin: "-45% 0px -50% 0px" });
secciones.forEach((s) => observador.observe(s));


// --- Portada: si no existe img/portada.jpg se muestra un semáforo ilustrado ---
document.querySelectorAll("img[data-respaldo]").forEach((img) => {
  const cambiar = () => {
    const ilus = document.createElement("div");
    ilus.className = "ilustracion";
    ilus.setAttribute("aria-hidden", "true");
    // Semáforo con el muñeco peatonal dentro de la luz roja
    ilus.innerHTML = `<div>
      <div class="caja"><span class="foco r"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONOS.action_walk}</svg></span><span class="foco a"></span><span class="foco v"></span></div>
      <div class="poste"></div>
    </div>`;
    img.replaceWith(ilus);
  };
  if (img.complete && img.naturalWidth === 0) cambiar();
  else img.addEventListener("error", cambiar);
});


// --- Imágenes y video que aún no existen: se muestra un recuadro con el nombre del archivo esperado ---
function recuadro(el) {
  const hueco = document.createElement("div");
  hueco.className = "hueco";
  hueco.innerHTML = `<div><b>Coloca aquí tu ${el.tagName === "VIDEO" ? "video" : "imagen"}</b>${el.dataset.hueco}</div>`;
  el.replaceWith(hueco);
}
document.querySelectorAll("img[data-hueco]").forEach((img) => {
  if (img.complete && img.naturalWidth === 0) recuadro(img);
  else img.addEventListener("error", () => recuadro(img));
});
document.querySelectorAll("video[data-hueco]").forEach((video) => {
  if (video.error) recuadro(video);
  else video.addEventListener("error", () => recuadro(video));
});


// --- Diagrama de bloques: entradas, proceso, salidas, supervision y vision ---
function dibujarBloques() {
  const svg = document.getElementById("svgBloques");
  if (!svg) return;
  const icono = (nombre, x, y) =>
    `<svg class="icono-nodo" x="${x}" y="${y}" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONOS[nombre]}</svg>`;

  // Cada bloque: categoria, icono, título y lista de elementos (con punto de color opcional)
  const bloque = (x, y, w, h, cat, ic, titulo, items, principal = false) => `
    <rect class="nodo${principal ? " principal" : ""}" x="${x}" y="${y}" width="${w}" height="${h}" rx="14"/>
    <text class="categoria" x="${x + 18}" y="${y + 24}">${cat}</text>
    ${icono(ic, x + 16, y + 34)}
    <text class="nodo-titulo" x="${x + 52}" y="${y + 53}">${titulo}</text>
    ${items.map(([texto, color], n) => `
      ${color ? `<circle cx="${x + 24}" cy="${y + 84 + n * 24}" r="6" style="fill:${color}"/>` : `<circle cx="${x + 24}" cy="${y + 84 + n * 24}" r="3" style="fill:var(--texto-suave)"/>`}
      <text class="item" x="${x + 38}" y="${y + 89 + n * 24}">${texto}</text>`).join("")}`;

  const linea = "stroke:var(--texto-suave);stroke-width:3;fill:none;stroke-linejoin:round";
  svg.innerHTML = `
    <defs>
      <marker id="punta" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" style="fill:var(--texto-suave)"/>
      </marker>
      <marker id="puntaAcento" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" style="fill:var(--acento)"/>
      </marker>
    </defs>

    <!-- Alimentacion hacia el LOGO! -->
    <line x1="500" y1="104" x2="500" y2="146" style="${linea}" marker-end="url(#punta)"/>
    <text class="etq" x="512" y="130">120 V AC</text>

    <!-- Entradas al LOGO! y salidas al semaforo -->
    <line x1="240" y1="235" x2="376" y2="235" style="${linea}" marker-end="url(#punta)"/>
    <line x1="624" y1="235" x2="756" y2="235" style="${linea}" marker-end="url(#punta)"/>
    <line x1="870" y1="330" x2="870" y2="368" style="${linea}" marker-end="url(#punta)"/>

    <!-- Ethernet S7 en ambos sentidos entre el LOGO! y la computadora -->
    <line x1="500" y1="334" x2="500" y2="404" style="stroke:var(--acento);stroke-width:3;stroke-dasharray:2 7;stroke-linecap:round" marker-start="url(#puntaAcento)" marker-end="url(#puntaAcento)"/>
    <text class="etq-s7" x="512" y="374">Ethernet S7</text>

    <!-- Camara por USB a la computadora -->
    <line x1="240" y1="485" x2="376" y2="485" style="stroke:var(--texto-suave);stroke-width:2;fill:none" marker-end="url(#punta)"/>
    <text class="etq" x="308" y="475" text-anchor="middle">USB</text>

    <!-- Tiempos sugeridos: solo informativos para el operador -->
    <line x1="624" y1="525" x2="756" y2="525" style="stroke:var(--texto-suave);stroke-width:3;fill:none;stroke-dasharray:9 7" marker-end="url(#punta)"/>
    <text class="etq" x="690" y="515" text-anchor="middle">Tiempos sugeridos</text>

    ${bloque(380, 20, 240, 84, "ALIMENTACIÓN", "action_zap", "Red eléctrica", [])}
    ${bloque(20, 150, 220, 170, "ENTRADAS", "device_button", "Pulsadores",
      [["I1 · Marcha"], ["I2 · Paro"], ["I3 · Cruce peatonal"]])}
    ${bloque(380, 150, 240, 184, "PROCESO", "status_cpu", "LOGO! 230RCE",
      [["Marcha / Paro (RS)"], ["Temporizadores"], ["Solicitud peatonal"], ["Señal intermitente"]], true)}
    ${bloque(760, 150, 220, 180, "SALIDAS", "action_plug", "Pilotos",
      [["Q1 · Verde", "#22c55e"], ["Q2 · Amarillo", "#facc15"], ["Q3 · Rojo", "#ef4444"], ["Q4 · Circuito activo", "#22b8cf"]])}
    ${bloque(760, 372, 220, 80, "RESULTADO", "nav_hmi", "Semáforo", [])}
    ${bloque(380, 408, 240, 160, "SUPERVISIÓN", "device_monitor", "App HMI (PC)",
      [["Supervisión y control"], ["Conteo de vehículos"], ["Estadísticas"]])}
    ${bloque(20, 420, 220, 120, "VISIÓN", "nav_camera", "Cámara", [["Video del tráfico"]])}
    ${bloque(760, 488, 220, 80, "OPERADOR", "action_file", "LOGO!Soft", [])}
  `;
}
dibujarBloques();


// --- Diagrama de comunicacion: router arriba con cable Ethernet al LOGO! y a la computadora ---
function dibujarRed() {
  const svg = document.getElementById("svgRed");
  if (!svg) return;
  const icono = (nombre, x, y) =>
    `<svg class="icono-nodo" x="${x}" y="${y}" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONOS[nombre]}</svg>`;

  // Cada equipo: posición, tamaño, icono y textos
  const nodo = (x, y, w, h, ic, titulo, sub) => `
    <rect class="nodo" x="${x}" y="${y}" width="${w}" height="${h}" rx="14"/>
    ${icono(ic, x + 16, y + 16)}
    <text class="nodo-titulo" x="${x + 54}" y="${y + 36}">${titulo}</text>
    <text class="nodo-sub" x="${x + 18}" y="${y + h - 18}">${sub}</text>`;

  const cable = "style=\"stroke:var(--texto-suave);stroke-width:3;fill:none;stroke-linejoin:round\"";
  svg.innerHTML = `
    <defs>
      <marker id="flecha" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" style="fill:var(--acento)"/>
      </marker>
    </defs>

    <!-- Cables Ethernet: del router hacia el LOGO! y hacia la computadora -->
    <path d="M440,116 V160 H165 V200" ${cable}/>
    <path d="M520,116 V160 H795 V200" ${cable}/>
    <text class="etq" x="300" y="150" text-anchor="middle">Cable Ethernet</text>
    <text class="etq" x="660" y="150" text-anchor="middle">Cable Ethernet</text>

    <!-- Comunicacion S7 entre la computadora y el LOGO! a traves del router -->
    <line x1="274" y1="254" x2="686" y2="254" style="stroke:var(--acento);stroke-width:3;stroke-dasharray:2 7;stroke-linecap:round" marker-start="url(#flecha)" marker-end="url(#flecha)"/>
    <text class="etq-s7" x="480" y="240" text-anchor="middle">Protocolo S7 (puerto 102)</text>
    <text class="etq" x="480" y="278" text-anchor="middle">a través del router</text>

    <!-- Salidas del LOGO! al semaforo y camara USB a la computadora -->
    <line x1="165" y1="296" x2="165" y2="340" ${cable}/>
    <text class="etq" x="177" y="323">Salidas Q1–Q4</text>
    <line x1="795" y1="296" x2="795" y2="340" style="stroke:var(--texto-suave);stroke-width:2;fill:none"/>
    <text class="etq" x="807" y="323">USB</text>

    ${nodo(375, 20, 210, 96, "device_router", "Router", "Red local 192.168.1.x")}
    ${nodo(60, 200, 210, 96, "status_cpu", "LOGO! 230RCE", "PLC · puerto Ethernet")}
    ${nodo(690, 200, 210, 96, "device_monitor", "Computadora", "App LOGO! Traffic HMI")}
    ${nodo(60, 340, 210, 84, "nav_hmi", "Semáforo", "Luces de 120 V")}
    ${nodo(690, 340, 210, 84, "nav_camera", "Cámara", "Conteo de vehículos")}
  `;
}
dibujarRed();


// --- Visor: al hacer clic en una imagen se muestra en grande ---
const visor = document.getElementById("visor");
const visorImagen = document.getElementById("visorImagen");

document.addEventListener("click", (ev) => {
  const img = ev.target.closest("img[data-zoom]");
  if (!img) return;
  visorImagen.src = img.src;
  visorImagen.alt = img.alt;
  // Las fotos con data-sin-texto se amplían sin descripción debajo
  document.getElementById("visorTexto").textContent = img.hasAttribute("data-sin-texto") ? "" : img.alt;
  visor.hidden = false;
});

function cerrarVisor() { visor.hidden = true; }
document.getElementById("visorCerrar").addEventListener("click", cerrarVisor);
visor.addEventListener("click", (ev) => { if (ev.target === visor) cerrarVisor(); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") cerrarVisor(); });
