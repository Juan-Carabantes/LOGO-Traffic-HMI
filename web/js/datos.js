// --- Temporizadores del programa del LOGO! (mismos valores que app/config/timers.conf) ---
// Para cambiar un tiempo en toda la web basta con editar "segundos" aquí.
const TEMPORIZADORES = [
  { bloque: "B3",  nombre: "Piloto verde",       salida: "Q1",    segundos: 80, descripcion: "Tiempo de la luz verde vehicular" },
  { bloque: "B21", nombre: "Piloto amarillo",    salida: "Q2",    segundos: 3,  descripcion: "Tiempo de la luz amarilla de precaución" },
  { bloque: "B6",  nombre: "Piloto rojo",        salida: "Q3",    segundos: 50, descripcion: "Luz roja del ciclo normal (sin solicitud peatonal)" },
  { bloque: "B13", nombre: "Cruce de peatones",  salida: "I3/M3", segundos: 45, descripcion: "Luz roja cuando se pidió el cruce peatonal" },
  { bloque: "B11", nombre: "Tiempo de parpadeo", salida: "Q4",    segundos: 3,  descripcion: "Parpadeo de la señal de advertencia" },
  { bloque: "B16", nombre: "Tiempo de parpadeo", salida: "Q2",    segundos: 5,  descripcion: "Amarillo intermitente de advertencia al arrancar" }
];

// --- Periodo de la señal intermitente (encendido y apagado, en segundos) ---
const PARPADEO_S = 0.5;

// --- Datos reales de la cámara (data/traffic_history.sqlite3, 23 y 24 de septiembre de 2026, hora de El Salvador) ---
const TRAFICO = {
  total: 1345,
  velocidadMedia: 27.2,
  sentidoA: 855,
  sentidoB: 489,
  ocupacionMaxima: 56,
  porTipo: [
    { tipo: "Autos",    cantidad: 1262, velocidad: 18.2 },
    { tipo: "Camiones", cantidad: 34,   velocidad: 24.0 },
    { tipo: "Buses",    cantidad: 27,   velocidad: 9.0 },
    { tipo: "Motos",    cantidad: 22,   velocidad: 4.6 }
  ],
  porIntervalo: [
    { etiqueta: "23 sep 14:40", cantidad: 105 },
    { etiqueta: "23 sep 14:50", cantidad: 46 },
    { etiqueta: "23 sep 15:20", cantidad: 64 },
    { etiqueta: "23 sep 16:20", cantidad: 51 },
    { etiqueta: "23 sep 16:30", cantidad: 262 },
    { etiqueta: "23 sep 16:40", cantidad: 329 },
    { etiqueta: "23 sep 16:50", cantidad: 251 },
    { etiqueta: "24 sep 11:30", cantidad: 237 }
  ]
};

// --- Reglas de tiempos sugeridos (copia de app/config/analytics.conf) ---
const REGLAS = {
  verde: { niveles: [[2, 1, 20], [6, 3, 30], [12, 5, 45], [18, 999, 60]], saturacion: 80,
           velocidadCongestion: 15, vehiculosCongestion: 3, extra: 15, maximo: 90 },
  amarillo: { alta: 50, segAlta: 5, media: 30, segMedia: 4, segBaja: 3 },
  rojo: { niveles: [[3, 25], [10, 35]], segAlto: 50 },
  peaton: { vehiculosCongestion: 5, segCongestion: 55, segNormal: 45 }
};

// --- Datos electricos del LOGO! 230RCE (hoja de datos de Siemens) ---
const LOGO_RELE = {
  corrienteResistiva: 10,   // A por salida
  corrienteInductiva: 3,    // A por salida
  lamparasIncandescentes: 500   // W por salida a 115/120 V
};

// --- Conductores: resistencia (ohm/km, NEC Cap. 9 Tabla 8) y límites de proteccion y ampacidad ---
const CONDUCTORES = {
  18: { resistencia: 25.5, proteccionMax: 7,  ampacidad: 6 },
  16: { resistencia: 16.0, proteccionMax: 10, ampacidad: 8 },
  14: { resistencia: 10.1, proteccionMax: 15, ampacidad: 15 }
};

// --- Valores comerciales de fusibles y breakers (A) ---
const PROTECCIONES = [1, 2, 3, 4, 5, 6, 10, 15, 20];

// --- Datos de diseño de la instalación (memoria de calculo) ---
// Potencias de referencia: se cambian aquí con los datos de placa de focos y pilotos.
const INSTALACION = {
  tension: 120,          // V
  semaforos: 2,          // semáforos conectados en paralelo a cada salida
  tipoFoco: "LED",
  potenciaFoco: 9,       // W por foco
  potenciaPiloto: 1,     // W por piloto Q4/Q5
  potenciaLogo: 4,       // W (aproximado)
  largoCable: 1,         // m hasta la luz más lejana
  calibre: 16,           // AWG
  horasUso: 8            // h de exposicion
};

// --- Datos de la bateria de la luz de emergencia ---
const BATERIA = {
  tension: 12,           // V
  potenciaLuz: 5,        // W de la luz ambar
  autonomia: 3,          // h
  cicloTrabajo: 50,      // % del tiempo encendida al parpadear
  descargaMaxima: 50     // % de descarga permitida
};
