// --- Iconos SVG del proyecto (mismo estilo que la app: 24x24, trazo 2, stroke="currentColor") ---
const ICONOS = {
  action_check: '<polyline points="20 6 9 17 4 12"></polyline>',
  action_file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path> <polyline points="14 2 14 8 20 8"></polyline>',
  action_play: '<polygon points="6 3 20 12 6 21 6 3"></polygon>',
  action_plug: '<path d="M9 2v6"></path> <path d="M15 2v6"></path> <path d="M6 8h12v3a6 6 0 0 1-12 0z"></path> <path d="M12 17v5"></path>',
  action_print: '<polyline points="6 9 6 2 18 2 18 9"></polyline> <rect x="6" y="14" width="12" height="8"></rect> <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>',
  action_ruler: '<path d="M21.3 8.7 15.3 2.7a1 1 0 0 0-1.4 0L2.7 13.9a1 1 0 0 0 0 1.4l6 6a1 1 0 0 0 1.4 0L21.3 10.1a1 1 0 0 0 0-1.4z"></path> <path d="M7.5 10.5l2 2"></path> <path d="M10.5 7.5l2 2"></path> <path d="M13.5 4.5l2 2"></path> <path d="M4.5 13.5l2 2"></path>',
  action_walk: '<circle cx="13" cy="4" r="2"></circle> <path d="M9 21l2.5-6.5L14 17v4"></path> <path d="M8 11l3-3.5 3 1.5 2 3"></path> <path d="M11 7.5l.5 7"></path>',
  action_zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>',
  nav_analytics: '<line x1="18" y1="20" x2="18" y2="10"></line> <line x1="12" y1="20" x2="12" y2="4"></line> <line x1="6" y1="20" x2="6" y2="14"></line> <line x1="2" y1="20" x2="22" y2="20"></line>',
  nav_camera: '<path d="M23 7l-7 5 7 5V7z"></path> <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>',
  nav_hmi: '<rect x="7" y="2" width="10" height="20" rx="3" ry="3"></rect> <circle cx="12" cy="7" r="1.6"></circle> <circle cx="12" cy="12" r="1.6"></circle> <circle cx="12" cy="17" r="1.6"></circle>',
  nav_home: '<path d="M3 11l9-8 9 8"></path> <path d="M5 10v10h14V10"></path> <path d="M10 20v-6h4v6"></path>',
  nav_menu: '<line x1="3" y1="12" x2="21" y2="12"></line> <line x1="3" y1="6" x2="21" y2="6"></line> <line x1="3" y1="18" x2="21" y2="18"></line>',
  nav_settings: '<circle cx="12" cy="12" r="3"></circle> <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>',
  nav_timer: '<circle cx="12" cy="13" r="8"></circle> <path d="M12 9v4l2.5 2.5"></path> <path d="M10 2h4"></path> <path d="M12 2v3"></path>',
  nav_users: '<circle cx="9" cy="8" r="3.5"></circle> <path d="M2 21v-1a6 6 0 0 1 12 0v1"></path> <circle cx="17" cy="9" r="2.5"></circle> <path d="M16 14.5a5 5 0 0 1 6 4.9V21"></path>',
  status_activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>',
  status_battery: '<rect x="2" y="7" width="17" height="10" rx="2"></rect> <line x1="22" y1="11" x2="22" y2="13"></line> <polyline points="11 9 9 12 12 12 10 15"></polyline>',
  status_bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"></path> <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>',
  status_box: '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"></path> <polyline points="3 8 12 13 21 8"></polyline> <line x1="12" y1="13" x2="12" y2="21"></line>',
  status_bulb: '<path d="M9 18h6"></path> <path d="M10 22h4"></path> <path d="M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 0 12 2z"></path>',
  status_cpu: '<rect x="4" y="4" width="16" height="16" rx="2"></rect> <rect x="9" y="9" width="6" height="6"></rect> <line x1="9" y1="1" x2="9" y2="4"></line> <line x1="15" y1="1" x2="15" y2="4"></line> <line x1="9" y1="20" x2="9" y2="23"></line> <line x1="15" y1="20" x2="15" y2="23"></line> <line x1="20" y1="9" x2="23" y2="9"></line> <line x1="20" y1="14" x2="23" y2="14"></line> <line x1="1" y1="9" x2="4" y2="9"></line> <line x1="1" y1="14" x2="4" y2="14"></line>',
  status_gauge: '<path d="M12 14l4-4"></path> <path d="M3.34 19a10 10 0 1 1 17.32 0"></path>',
  status_palette: '<circle cx="13.5" cy="6.5" r="1"></circle> <circle cx="17.5" cy="10.5" r="1"></circle> <circle cx="8.5" cy="7.5" r="1"></circle> <circle cx="6.5" cy="12.5" r="1"></circle> <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.9 0 1.7-.8 1.7-1.7 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1 0-.9.8-1.7 1.7-1.7H17c2.8 0 5-2.2 5-5C22 6 17.5 2 12 2z"></path>',
  status_road: '<path d="M4 21L8 3"></path> <path d="M20 21L16 3"></path> <path d="M12 5v2"></path> <path d="M12 11v2"></path> <path d="M12 17v2"></path>',
  status_shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path> <polyline points="9 12 11 14 15 10"></polyline>',
  status_trend: '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline> <polyline points="17 6 23 6 23 12"></polyline>',
  status_wave: '<polyline points="2 16 2 8 6 8 6 16 10 16 10 8 14 8 14 16 18 16 18 8 22 8"></polyline>',
  theme_moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path>',
  theme_sun: '<circle cx="12" cy="12" r="4"></circle> <path d="M12 2v2"></path> <path d="M12 20v2"></path> <path d="M4.93 4.93l1.41 1.41"></path> <path d="M17.66 17.66l1.41 1.41"></path> <path d="M2 12h2"></path> <path d="M20 12h2"></path> <path d="M6.34 17.66l-1.41 1.41"></path> <path d="M19.07 4.93l-1.41 1.41"></path>',
  device_router: '<rect x="2" y="14" width="20" height="7" rx="2"></rect> <line x1="6" y1="17.5" x2="6.01" y2="17.5"></line> <line x1="10" y1="17.5" x2="10.01" y2="17.5"></line> <path d="M12 14v-3"></path> <path d="M8.5 8a5 5 0 0 1 7 0"></path> <path d="M6 5a8.5 8.5 0 0 1 12 0"></path>',
  device_monitor: '<rect x="2" y="3" width="20" height="14" rx="2"></rect> <line x1="8" y1="21" x2="16" y2="21"></line> <line x1="12" y1="17" x2="12" y2="21"></line>',
  device_button: '<circle cx="12" cy="12" r="9"></circle> <circle cx="12" cy="12" r="4"></circle>',
  device_panel: '<rect x="3" y="2" width="18" height="20" rx="2"></rect> <line x1="7" y1="7" x2="17" y2="7"></line> <line x1="7" y1="12" x2="17" y2="12"></line> <line x1="7" y1="17" x2="12" y2="17"></line>',
  action_stand: '<circle cx="12" cy="4" r="2"></circle> <path d="M12 7v8"></path> <path d="M8 10l4-2 4 2"></path> <path d="M10 21l2-6 2 6"></path>'
};

// --- Coloca cada icono dentro de los elementos que tienen data-icono ---
function pintarIconos(raiz = document) {
  raiz.querySelectorAll("[data-icono]").forEach((el) => {
    const cuerpo = ICONOS[el.dataset.icono];
    if (!cuerpo) return;
    el.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${cuerpo}</svg>`;
  });
}
