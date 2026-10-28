/**
 * ============================================================================
 * AI TUTOR CÁLCULO — CLIENTE v2
 * ============================================================================
 * Layout de 3 paneles:
 *   - Izquierda: historial de conversaciones guardadas + texto explicativo
 *   - Centro:    pizarra matemática (solo fórmulas LaTeX renderizadas)
 *   - Derecha:   chat compacto con el tutor
 *
 * Sistema de memoria con localStorage para persistir conversaciones.
 * Pipeline de renderizado: Placeholders → Marked → DOMPurify → KaTeX.
 */

// ============================================================================
// 1. ESTADO GLOBAL Y CONSTANTES
// ============================================================================

const STORAGE_KEY = 'tutor_calculo_data';
const MAX_CHARS = 3000;

/**
 * Estructura almacenada en localStorage:
 * {
 *   conversaciones: [{ id, titulo, fecha, mensajes: [{rol, contenido}] }],
 *   conversacionActiva: "id" | null
 * }
 */
let appState = {
  conversaciones: [],
  conversacionActiva: null
};

let estaCargando = false;

// ============================================================================
// 2. REFERENCIAS AL DOM
// ============================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const sidebarToggle     = $('#sidebarToggle');
const leftPanel         = $('#leftPanel');
const newChatBtn        = $('#newChatBtn');
const conversationsList = $('#conversationsList');
const textSection       = $('#textSection');
const textContentArea   = $('#textContentArea');
const textPlaceholder   = $('#textPlaceholder');
const expandTextBtn     = $('#expandTextBtn');
const centerPanel       = $('#centerPanel');
const pizarraWelcome    = $('#pizarraWelcome');
const pizarraContent    = $('#pizarraContent');
const pizarraHeader     = $('#pizarraHeader');
const pizarraMath       = $('#pizarraMath');
const chatMessages      = $('#chatMessages');
const loadingIndicator  = $('#loadingIndicator');
const chatForm          = $('#chatForm');
const userInput         = $('#userInput');
const sendBtn           = $('#sendBtn');
const charCounter       = $('#charCounter');
const statusIndicator   = $('#statusIndicator');
const clearChatBtn      = $('#clearChatBtn');
const textOverlay       = $('#textOverlay');
const textOverlayBody   = $('#textOverlayBody');
const closeOverlayBtn   = $('#closeOverlayBtn');

// ============================================================================
// 3. PERSISTENCIA CON localStorage
// ============================================================================

/** Carga el estado desde localStorage */
function cargarEstado() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      appState.conversaciones = parsed.conversaciones || [];
      appState.conversacionActiva = parsed.conversacionActiva || null;
    }
  } catch (e) {
    console.warn('Error al cargar estado desde localStorage:', e);
  }
}

/** Guarda el estado actual en localStorage */
function guardarEstado() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(appState));
  } catch (e) {
    console.warn('Error al guardar estado en localStorage:', e);
  }
}

/** Genera un ID único sencillo */
function generarId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 6);
}

/** Escapa texto plano para insertarlo en HTML (contenido o atributos) */
function escaparHTML(texto) {
  return String(texto).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
}

/** Crea una nueva conversación vacía y la activa */
function crearNuevaConversacion() {
  const conv = {
    id: generarId(),
    titulo: 'Nueva conversación',
    fecha: new Date().toISOString(),
    mensajes: []
  };
  appState.conversaciones.unshift(conv);
  appState.conversacionActiva = conv.id;
  guardarEstado();
  renderizarListaConversaciones();
  limpiarPaneles();
}

/** Obtiene la conversación activa actual */
function getConversacionActiva() {
  return appState.conversaciones.find(c => c.id === appState.conversacionActiva) || null;
}

/** Cambia a una conversación existente */
function activarConversacion(id) {
  appState.conversacionActiva = id;
  guardarEstado();
  renderizarListaConversaciones();
  restaurarConversacion(id);
}

/** Elimina una conversación por ID */
function eliminarConversacion(id) {
  appState.conversaciones = appState.conversaciones.filter(c => c.id !== id);
  if (appState.conversacionActiva === id) {
    appState.conversacionActiva = appState.conversaciones.length > 0
      ? appState.conversaciones[0].id
      : null;
  }
  guardarEstado();
  renderizarListaConversaciones();
  if (appState.conversacionActiva) {
    restaurarConversacion(appState.conversacionActiva);
  } else {
    limpiarPaneles();
  }
}

// ============================================================================
// 4. PIPELINE DE RENDERIZADO MATEMÁTICO
// ============================================================================

/**
 * Pipeline robusto de Markdown + LaTeX:
 * 1. Extraer fórmulas a placeholders → 2. Marked → 3. Re-inyectar → 4. DOMPurify
 */
function renderizarMarkdownConMath(texto) {
  if (!texto) return '';
  const mathBlocks = [];

  // Paso 1a: Extraer bloques display $$...$$
  let procesado = texto.replace(/\$\$([\s\S]+?)\$\$/g, (_, eq) => {
    const ph = `%%MATH_D_${mathBlocks.length}%%`;
    mathBlocks.push({ tipo: 'display', contenido: eq.trim() });
    return ph;
  });

  // Paso 1b: Extraer fórmulas inline $...$
  procesado = procesado.replace(/(?<!\\)\$(?!\$)(.+?)(?<!\\)\$/g, (_, eq) => {
    const ph = `%%MATH_I_${mathBlocks.length}%%`;
    mathBlocks.push({ tipo: 'inline', contenido: eq.trim() });
    return ph;
  });

  // Paso 2: Parsear Markdown
  let html = marked.parse(procesado, { gfm: true, breaks: true });

  // Paso 3: Re-inyectar fórmulas
  mathBlocks.forEach((b, i) => {
    const tag = b.tipo === 'display' ? `$$${b.contenido}$$` : `$${b.contenido}$`;
    // Función como reemplazo: con un string, replace() interpretaría "$$" como "$"
    html = html.replace(b.tipo === 'display' ? `%%MATH_D_${i}%%` : `%%MATH_I_${i}%%`, () => tag);
  });

  // Paso 4: Sanitizar
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['span', 'div', 'math', 'semantics', 'annotation', 'mrow', 'mi', 'mo', 'mtext'],
    ADD_ATTR: ['class', 'style', 'aria-hidden', 'role']
  });
}

/** Ejecuta KaTeX sobre un nodo del DOM */
function ejecutarKaTeX(nodo) {
  if (typeof renderMathInElement === 'function') {
    renderMathInElement(nodo, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$',  right: '$',  display: false }
      ],
      throwOnError: false,
      errorColor: '#f87171',
      ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
    });
  }
}

// ============================================================================
// 5. SEPARACIÓN DE CONTENIDO: MATH vs TEXTO
// ============================================================================

/**
 * Extrae los bloques display math ($$...$$) de una respuesta del tutor.
 * Devuelve: { mathBlocks: string[], textoConContexto: string[] }
 *
 * Los mathBlocks se renderizan en la pizarra central.
 * textoConContexto se renderiza con Markdown+KaTeX en el panel izquierdo.
 */
function separarContenido(texto) {
  const mathBlocks = [];
  const regex = /\$\$([\s\S]+?)\$\$/g;
  let match;

  while ((match = regex.exec(texto)) !== null) {
    mathBlocks.push(match[1].trim());
  }

  return { mathBlocks, textoCompleto: texto };
}

// ============================================================================
// 6. RENDERIZADO DE PANELES
// ============================================================================

/** Limpia los 3 paneles a su estado inicial */
function limpiarPaneles() {
  detenerNarracion();
  chatMessages.innerHTML = '';
  pizarraWelcome.style.display = '';
  pizarraContent.classList.add('hidden');
  pizarraMath.innerHTML = '';
  pizarraHeader.innerHTML = '';
  textContentArea.innerHTML = '';
  textContentArea.appendChild(textPlaceholder || crearPlaceholder());
}

function crearPlaceholder() {
  const div = document.createElement('div');
  div.className = 'text-placeholder';
  div.id = 'textPlaceholder';
  div.innerHTML = '<p>La explicación paso a paso aparecerá aquí cuando envíes una consulta.</p>';
  return div;
}

/**
 * Sello con el resultado de la comprobación simbólica hecha por SymPy en el backend.
 * verificacion: { estado: 'verificado' | 'discrepancia' | 'no_verificable', sympy: latex | null }
 */
function selloVerificacion(verificacion) {
  if (!verificacion) return '';
  const textos = {
    verificado: '✅ Resultado verificado con SymPy',
    discrepancia: '⚠️ SymPy obtuvo un resultado distinto',
    no_verificable: '❔ SymPy no pudo verificar este resultado'
  };
  const texto = textos[verificacion.estado];
  if (!texto) return '';
  const valor = verificacion.sympy ? `: $${escaparHTML(verificacion.sympy)}$` : '';
  return `<div class="verif-sello verif-${verificacion.estado}">${texto}${valor}</div>`;
}

// Colores de las series (paleta categórica, variante para fondo oscuro), en orden fijo
const COLORES_SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500'];
const COLOR_TANGENTE = '#9085e9';
const ESTILO_EJES = { gridcolor: '#222222', zerolinecolor: '#383838', linecolor: '#383838', color: '#a0a0a0' };

/**
 * Dibuja con Plotly una gráfica cuyos puntos ya calculó SymPy en el backend (graficador.py).
 * grafica 2D: { tipo: '2d', trazos: [{ estilo: 'curva'|'area'|'tangente'|'punto', nombre, x, y }], rango_y }
 * grafica 3D: { tipo: '3d', nombre, x, y, z, plano?: { nombre, z }, punto?: { x, y, z } }
 */
function dibujarGrafica(contenedor, grafica) {
  if (typeof Plotly === 'undefined') return;  // CDN no disponible: la pizarra sigue funcionando sin gráfica

  const layout = {
    paper_bgcolor: '#141414', plot_bgcolor: '#141414',
    font: { family: 'Inter, sans-serif', color: '#a0a0a0', size: 12 },
    margin: { l: 48, r: 16, t: 16, b: 40 },
    legend: { orientation: 'h', y: -0.15, font: { color: '#ffffff' } },
    hoverlabel: { bgcolor: '#1c1c1c', bordercolor: '#383838', font: { color: '#ffffff' } }
  };
  let trazos;

  if (grafica.tipo === '3d') {
    trazos = [{
      type: 'surface', name: grafica.nombre, x: grafica.x, y: grafica.y, z: grafica.z,
      // Escala secuencial de un solo tono (azul), de oscuro a claro según la altura
      colorscale: [[0, '#0d2a52'], [1, '#86b6ef']], showscale: false, opacity: 0.95,
      hovertemplate: 'x = %{x:.3f}<br>y = %{y:.3f}<br>z = %{z:.3f}<extra></extra>'
    }];
    if (grafica.plano) {
      trazos.push({
        type: 'surface', name: grafica.plano.nombre, x: grafica.x, y: grafica.y, z: grafica.plano.z,
        colorscale: [[0, COLOR_TANGENTE], [1, COLOR_TANGENTE]], showscale: false, opacity: 0.55,
        hovertemplate: `${escaparHTML(grafica.plano.nombre)}<br>z = %{z:.3f}<extra></extra>`
      });
    }
    if (grafica.punto) {
      trazos.push({
        type: 'scatter3d', mode: 'markers', name: 'Punto de tangencia',
        x: [grafica.punto.x], y: [grafica.punto.y], z: [grafica.punto.z],
        marker: { size: 6, color: '#ffffff', line: { color: '#141414', width: 2 } }
      });
    }
    layout.scene = {
      bgcolor: '#141414',
      aspectmode: 'cube',                         // Ejes de igual tamaño: la forma no se deforma
      camera: { eye: { x: 1.6, y: -1.6, z: 1.1 } }, // Vista en diagonal desde arriba
      xaxis: { ...ESTILO_EJES, title: 'x' }, yaxis: { ...ESTILO_EJES, title: 'y' }, zaxis: { ...ESTILO_EJES, title: 'z' }
    };
    layout.margin = { l: 0, r: 0, t: 0, b: 0 };
  } else {
    let serie = 0;
    trazos = grafica.trazos.map(t => {
      const base = { type: 'scatter', name: t.nombre, x: t.x, y: t.y, connectgaps: false };
      if (t.estilo === 'area') {
        return { ...base, mode: 'lines', fill: 'tozeroy', line: { color: COLORES_SERIES[0], width: 0 },
                 fillcolor: 'rgba(57, 135, 229, 0.3)' };
      }
      if (t.estilo === 'tangente') {
        return { ...base, mode: 'lines', line: { color: COLOR_TANGENTE, width: 2, dash: 'dash' } };
      }
      if (t.estilo === 'punto') {
        return { ...base, mode: 'markers', marker: { size: 10, color: '#ffffff', line: { color: '#141414', width: 2 } } };
      }
      return { ...base, mode: 'lines', line: { color: COLORES_SERIES[serie++ % COLORES_SERIES.length], width: 2 } };
    });
    layout.xaxis = { ...ESTILO_EJES };
    layout.yaxis = { ...ESTILO_EJES, ...(grafica.rango_y ? { range: grafica.rango_y } : {}) };
    layout.hovermode = 'x unified';
    layout.showlegend = trazos.length > 1;
  }

  Plotly.newPlot(contenedor, trazos, layout, { responsive: true, displaylogo: false });
}

// ============================================================================
// NARRACIÓN POR VOZ (Web Speech API del navegador, sin librerías)
// ============================================================================

const vozDisponible = 'speechSynthesis' in window;
let narracionId = 0;  // Invalida los eventos de una narración anterior al detenerla o reiniciarla

function vozEspanol() {
  const voces = speechSynthesis.getVoices();
  return voces.find(v => v.lang === 'es-MX') || voces.find(v => v.lang.startsWith('es')) || null;
}

function quitarEnfoque() {
  document.querySelectorAll('.enfocado').forEach(el => el.classList.remove('enfocado'));
}

function detenerNarracion() {
  narracionId++;
  if (vozDisponible) speechSynthesis.cancel();
  quitarEnfoque();
  const boton = document.getElementById('btnNarrar');
  if (boton) {
    boton.textContent = '🔊 Escuchar explicación';
    boton.dataset.narrando = '';
  }
  document.getElementById('narracionSubtitulo')?.classList.add('hidden');
}

/** Lee los pasos uno por uno, resaltando en la pizarra la gráfica o fórmula de cada paso */
function narrar(pasos) {
  detenerNarracion();
  const id = narracionId;
  const boton = document.getElementById('btnNarrar');
  const subtitulo = document.getElementById('narracionSubtitulo');
  boton.textContent = '⏹ Detener';
  boton.dataset.narrando = '1';
  subtitulo.classList.remove('hidden');

  const voz = vozEspanol();
  const grafica = pizarraMath.querySelector('.grafica-block');
  // El foco es el LaTeX de una fórmula, a veces resumido por la IA (ej. omite pasos intermedios).
  // Se compara sin espacios ni '&': comienzo exacto, luego contenido, luego el prefijo común más largo.
  const normalizar = (t) => t.replace(/\\[,;!: ]|[\s&]/g, '');
  const formulas = [...pizarraMath.querySelectorAll('.math-block')].map(el => ({ el, latex: normalizar(el.dataset.latex || '') }));
  const prefijoComun = (a, b) => { let i = 0; while (i < a.length && a[i] === b[i]) i++; return i; };
  const buscarFormula = (foco) => {
    const f = normalizar(foco);
    if (!f) return null;
    const exacta = formulas.find(x => x.latex.startsWith(f)) || formulas.find(x => x.latex.includes(f));
    if (exacta) return exacta.el;
    let mejor = null, largo = 3;  // Mínimo 4 caracteres en común para no resaltar algo al azar
    formulas.forEach(x => { const n = prefijoComun(f, x.latex); if (n > largo) { mejor = x; largo = n; } });
    return mejor?.el || null;
  };

  pasos.forEach((paso, i) => {
    // Una frase por paso: Chrome corta las locuciones muy largas
    const locucion = new SpeechSynthesisUtterance(paso.texto);
    locucion.lang = voz ? voz.lang : 'es-ES';
    if (voz) locucion.voice = voz;
    locucion.onstart = () => {
      if (id !== narracionId) return;
      quitarEnfoque();
      const elemento = paso.foco === 'grafica' ? grafica : (paso.foco ? buscarFormula(paso.foco) : null);
      if (elemento) {
        elemento.classList.add('enfocado');
        elemento.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      subtitulo.textContent = paso.texto;  // Subtítulo: también sirve a quien no puede escuchar
    };
    if (i === pasos.length - 1) {
      locucion.onend = () => { if (id === narracionId) detenerNarracion(); };
    }
    speechSynthesis.speak(locucion);
  });
}

/**
 * Muestra la respuesta en la pizarra central: gráfica (si hay) y bloques math.
 * extras: { verificacion, grafica, narracion } tal como los devolvió /api/chat
 */
function mostrarEnPizarra(mathBlocks, titulo, extras = {}) {
  pizarraWelcome.style.display = 'none';
  pizarraContent.classList.remove('hidden');
  detenerNarracion();

  // Header
  const controlesVoz = extras.narracion && vozDisponible
    ? `<button id="btnNarrar" class="btn-narrar" type="button">🔊 Escuchar explicación</button>
       <div id="narracionSubtitulo" class="narracion-subtitulo hidden" aria-live="polite"></div>`
    : '';
  pizarraHeader.innerHTML = `<h2>${escaparHTML(titulo)}</h2>${selloVerificacion(extras.verificacion)}${controlesVoz}`;
  ejecutarKaTeX(pizarraHeader);
  document.getElementById('btnNarrar')?.addEventListener('click', (e) => {
    if (e.currentTarget.dataset.narrando) detenerNarracion();
    else narrar(extras.narracion.pasos);
  });

  // Limpiar y pintar bloques
  pizarraMath.innerHTML = '';

  if (extras.grafica) {
    const bloque = document.createElement('div');
    bloque.className = 'grafica-block';
    pizarraMath.appendChild(bloque);  // Plotly necesita el contenedor ya en el DOM para medirlo
    dibujarGrafica(bloque, extras.grafica);
  }

  if (mathBlocks.length === 0) {
    if (extras.grafica) return;
    const noMath = document.createElement('div');
    noMath.className = 'math-inline-block';
    noMath.innerHTML = '<p style="text-align:center; color: var(--text-muted);">No se detectaron fórmulas display en esta respuesta.</p>';
    pizarraMath.appendChild(noMath);
    return;
  }

  mathBlocks.forEach(latex => {
    const block = document.createElement('div');
    block.className = 'math-block';
    block.dataset.latex = latex;  // Para que la narración encuentre esta fórmula
    block.innerHTML = `$$${latex}$$`;
    pizarraMath.appendChild(block);
    ejecutarKaTeX(block);
  });
}

/** Muestra la explicación textual en el panel izquierdo */
function mostrarTextoExplicativo(textoCompleto) {
  const ph = textContentArea.querySelector('.text-placeholder');
  if (ph) ph.remove();

  textContentArea.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'tutor-text-rendered';
  div.innerHTML = renderizarMarkdownConMath(textoCompleto);
  textContentArea.appendChild(div);
  ejecutarKaTeX(div);
}

// --- Último texto del tutor guardado para el overlay ---
let ultimoTextoTutor = '';

/** Muestra el overlay con la explicación expandida */
function mostrarOverlayTexto() {
  if (!ultimoTextoTutor) return;
  textOverlay.classList.remove('hidden');
  textOverlayBody.innerHTML = renderizarMarkdownConMath(ultimoTextoTutor);
  ejecutarKaTeX(textOverlayBody);
}

function cerrarOverlayTexto() {
  textOverlay.classList.add('hidden');
}

// ============================================================================
// 7. CHAT (PANEL DERECHO)
// ============================================================================

/** Agrega un mensaje al panel de chat */
function agregarMensajeChat(rol, contenido, opts = {}) {
  const msg = document.createElement('div');
  const claseRol = rol === 'usuario' ? 'user-msg' : (rol === 'error' ? 'error-msg' : 'tutor-msg');
  msg.className = `chat-msg ${claseRol}`;

  const autorLabel = rol === 'usuario' ? 'Tú:' : (rol === 'error' ? 'Sistema:' : 'AI:');
  const autorClass = rol === 'usuario' ? 'user' : (rol === 'error' ? 'error' : 'tutor');

  let bodyHTML = '';
  if (rol === 'usuario') {
    bodyHTML = `<div class="chat-msg-body">${escaparHTML(contenido).replace(/\n/g, '<br>')}</div>`;
  } else if (rol === 'error') {
    bodyHTML = `<div class="chat-msg-body">⚠️ ${escaparHTML(contenido)}</div>`;
  } else {
    // Tutor: renderizar con Markdown + KaTeX, hacerlo clickable
    const htmlRenderizado = renderizarMarkdownConMath(contenido);
    bodyHTML = `<div class="chat-msg-body" data-raw="${encodeURIComponent(contenido)}">
      ${htmlRenderizado}
      ${selloVerificacion(opts.verificacion)}
      <button class="msg-copy-btn" title="Copiar respuesta">📋 Copiar</button>
    </div>`;
  }

  msg.innerHTML = `
    <div class="chat-msg-author ${autorClass}">${autorLabel}</div>
    ${bodyHTML}
  `;

  chatMessages.appendChild(msg);

  // Ejecutar KaTeX si es del tutor
  if (rol === 'tutor') {
    const body = msg.querySelector('.chat-msg-body');
    ejecutarKaTeX(body);

    // Click en mensaje del tutor → mostrar en pizarra
    body.addEventListener('click', (e) => {
      if (e.target.closest('.msg-copy-btn')) return; // No al click en copiar
      const raw = decodeURIComponent(body.dataset.raw);
      const { mathBlocks } = separarContenido(raw);
      mostrarEnPizarra(mathBlocks, 'Respuesta Seleccionada', opts);
      mostrarTextoExplicativo(raw);
      ultimoTextoTutor = raw;
    });

    // Botón copiar
    const copyBtn = msg.querySelector('.msg-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        copiarAlPortapapeles(contenido, copyBtn);
      });
    }
  }

  chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
}

async function copiarAlPortapapeles(texto, boton) {
  try {
    await navigator.clipboard.writeText(texto);
    boton.textContent = '✓ Copiado';
    boton.classList.add('copied');
    setTimeout(() => {
      boton.textContent = '📋 Copiar';
      boton.classList.remove('copied');
    }, 2000);
  } catch (e) {
    console.error('Error al copiar:', e);
  }
}

// ============================================================================
// 8. LISTA DE CONVERSACIONES (SIDEBAR)
// ============================================================================

function renderizarListaConversaciones() {
  conversationsList.innerHTML = '';

  if (appState.conversaciones.length === 0) {
    conversationsList.innerHTML = '<div class="conversations-empty">Sin conversaciones guardadas</div>';
    return;
  }

  appState.conversaciones.forEach(conv => {
    const item = document.createElement('div');
    item.className = `conv-item ${conv.id === appState.conversacionActiva ? 'active' : ''}`;
    item.innerHTML = `
      <span class="conv-icon">💬</span>
      <span class="conv-title" title="${escaparHTML(conv.titulo)}">${escaparHTML(conv.titulo)}</span>
      <button class="conv-delete" title="Eliminar conversación" data-id="${conv.id}">✕</button>
    `;

    item.addEventListener('click', (e) => {
      if (e.target.closest('.conv-delete')) return;
      activarConversacion(conv.id);
    });

    const deleteBtn = item.querySelector('.conv-delete');
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      eliminarConversacion(conv.id);
    });

    conversationsList.appendChild(item);
  });
}

/** Restaura una conversación guardada en los paneles */
function restaurarConversacion(id) {
  const conv = appState.conversaciones.find(c => c.id === id);
  if (!conv) return;

  chatMessages.innerHTML = '';
  let ultimaRespuestaTutor = null;

  conv.mensajes.forEach(msg => {
    agregarMensajeChat(msg.rol, msg.contenido, { verificacion: msg.verificacion, grafica: msg.grafica, narracion: msg.narracion });
    if (msg.rol === 'tutor') {
      ultimaRespuestaTutor = msg;
    }
  });

  // Mostrar la última respuesta del tutor en la pizarra y texto
  if (ultimaRespuestaTutor) {
    const { mathBlocks } = separarContenido(ultimaRespuestaTutor.contenido);
    mostrarEnPizarra(mathBlocks, conv.titulo, ultimaRespuestaTutor);
    mostrarTextoExplicativo(ultimaRespuestaTutor.contenido);
    ultimoTextoTutor = ultimaRespuestaTutor.contenido;
  } else {
    limpiarPaneles();
    // Re-pintar mensajes si los hay
    conv.mensajes.forEach(msg => agregarMensajeChat(msg.rol, msg.contenido));
  }
}

// ============================================================================
// 9. COMUNICACIÓN CON EL BACKEND
// ============================================================================

async function enviarMensaje(textoMensaje) {
  const texto = textoMensaje.trim();
  if (!texto || estaCargando) return;

  if (!navigator.onLine) {
    agregarMensajeChat('error', 'No tienes conexión a internet. Revisa tu red e intenta de nuevo.');
    return;
  }

  // Asegurar que hay conversación activa
  let conv = getConversacionActiva();
  if (!conv) {
    crearNuevaConversacion();
    conv = getConversacionActiva();
  }

  // Auto-titulo: usar las primeras palabras del primer mensaje del usuario
  if (conv.mensajes.length === 0) {
    conv.titulo = texto.substring(0, 50) + (texto.length > 50 ? '...' : '');
    guardarEstado();
    renderizarListaConversaciones();
  }

  // Agregar mensaje al historial y al chat
  conv.mensajes.push({ rol: 'usuario', contenido: texto });
  guardarEstado();
  agregarMensajeChat('usuario', texto);

  // Limpiar input
  userInput.value = '';
  ajustarAlturaTextarea();
  actualizarContador();

  // Estado de carga
  setEstadoCarga(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensajes: conv.mensajes })
    });

    const data = await res.json();

    if (!res.ok) {
      // Los errores 422 de FastAPI traen detail como lista de objetos {msg, ...}
      const errMsg = Array.isArray(data.detail)
        ? data.detail.map(d => d.msg).join(' ')
        : (data.detail || 'Error al comunicarse con el tutor.');
      agregarMensajeChat('error', errMsg);
      conv.mensajes.pop(); // Quitar el mensaje fallido
      guardarEstado();
    } else {
      const { respuesta, verificacion, grafica, narracion } = data;

      // Guardar respuesta del tutor (el backend ignora verificacion, grafica y narracion en el historial)
      conv.mensajes.push({ rol: 'tutor', contenido: respuesta, verificacion, grafica, narracion });
      conv.fecha = new Date().toISOString();
      guardarEstado();

      // Mostrar en chat
      agregarMensajeChat('tutor', respuesta, { verificacion, grafica, narracion });

      // Separar math y mostrar en pizarra + panel de texto
      const { mathBlocks } = separarContenido(respuesta);
      mostrarEnPizarra(mathBlocks, conv.titulo, { verificacion, grafica, narracion });
      mostrarTextoExplicativo(respuesta);
      ultimoTextoTutor = respuesta;
    }
  } catch (err) {
    console.error('Error de red:', err);
    agregarMensajeChat('error', 'Error de comunicación con el servidor. ¿Está ejecutándose?');
    conv.mensajes.pop();
    guardarEstado();
  } finally {
    setEstadoCarga(false);
  }
}

function setEstadoCarga(carga) {
  estaCargando = carga;
  loadingIndicator.classList.toggle('hidden', !carga);
  sendBtn.disabled = carga;
  userInput.disabled = carga;
  if (!carga) userInput.focus();
  chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
}

// ============================================================================
// 10. UTILIDADES DE UI
// ============================================================================

function ajustarAlturaTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
}

function actualizarContador() {
  const len = userInput.value.length;
  charCounter.textContent = `${len}/${MAX_CHARS}`;
  charCounter.style.color = len > 2800 ? 'var(--c-error)' : '';
}

async function verificarEstado() {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    const dot = statusIndicator.querySelector('.status-dot');
    if (data.api_key_configured) {
      dot.className = 'status-dot online';
      statusIndicator.title = `Modelo: ${data.model}`;
    } else {
      dot.className = 'status-dot offline';
      statusIndicator.title = 'Sin API Key configurada';
    }
  } catch {
    const dot = statusIndicator.querySelector('.status-dot');
    dot.className = 'status-dot offline';
    statusIndicator.title = 'Servidor desconectado';
  }
}

// ============================================================================
// 11. EVENT LISTENERS
// ============================================================================

// Formulario de chat
chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  enviarMensaje(userInput.value);
});

// Enter = enviar, Shift+Enter = nueva línea
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    enviarMensaje(userInput.value);
  }
});

// Textarea dinámica
userInput.addEventListener('input', () => {
  ajustarAlturaTextarea();
  actualizarContador();
});

// Toggle sidebar en mobile
sidebarToggle.addEventListener('click', () => {
  const isMobile = window.innerWidth <= 1024;
  if (isMobile) {
    leftPanel.classList.toggle('open');
  } else {
    leftPanel.classList.toggle('collapsed');
  }
});

// Nueva conversación
newChatBtn.addEventListener('click', () => {
  crearNuevaConversacion();
});

// Limpiar chat actual
clearChatBtn.addEventListener('click', () => {
  const conv = getConversacionActiva();
  if (conv) {
    conv.mensajes = [];
    conv.titulo = 'Conversación vacía';
    guardarEstado();
    renderizarListaConversaciones();
    limpiarPaneles();
  }
});

// Expandir texto
expandTextBtn.addEventListener('click', mostrarOverlayTexto);
closeOverlayBtn.addEventListener('click', cerrarOverlayTexto);
textOverlay.addEventListener('click', (e) => {
  if (e.target === textOverlay) cerrarOverlayTexto();
});

// Escape para cerrar overlay
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') cerrarOverlayTexto();
});

// Ejemplos de la pizarra de bienvenida
document.querySelectorAll('.example-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const prompt = btn.getAttribute('data-prompt');
    if (prompt) {
      userInput.value = prompt;
      ajustarAlturaTextarea();
      actualizarContador();
      enviarMensaje(prompt);
    }
  });
});

// ============================================================================
// 12. INICIALIZACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // 1. Cargar estado guardado
  cargarEstado();

  // 2. Si no hay conversaciones, crear una por defecto
  if (appState.conversaciones.length === 0) {
    crearNuevaConversacion();
  } else {
    renderizarListaConversaciones();
    // Restaurar la conversación activa
    if (appState.conversacionActiva) {
      restaurarConversacion(appState.conversacionActiva);
    }
  }

  // 3. Renderizar KaTeX en las tarjetas de ejemplo
  if (pizarraWelcome) ejecutarKaTeX(pizarraWelcome);

  // 4. Verificar servidor
  verificarEstado();

  // 5. Foco inicial
  userInput.focus();
});
