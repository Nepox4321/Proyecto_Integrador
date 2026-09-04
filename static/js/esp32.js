/* ============================================================
   AutoNova · esp32.js — Monitoreo en TIEMPO REAL del ESP32
   Consulta el endpoint /api/esp de la app Flask cada N segundos
   y actualiza las tarjetas del panel (estado + cronómetro) sin
   recargar la página. Las tarjetas se identifican por data-codigo.
   ============================================================ */

const ESP_REFRESH_MS = 3000;                // intervalo de polling
const STATUS_CLASSES = {
  conectado: 'ok',
  esperando: 'warn',
  apagado: 'off',
  offline: 'off'
};

// --- Formatea un timestamp (ms) como HH:MM:SS transcurrido ---
function fmtElapsed(fromMs) {
  const s = Math.max(0, Math.floor((Date.now() - fromMs) / 1000));
  const h = String(Math.floor(s / 3600)).padStart(2, '0');
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const sec = String(s % 60).padStart(2, '0');
  return `${h}:${m}:${sec}`;
}

/* --- Semáforo del módulo (verde/azul/amarillo/rojo) --- */
const SEM_COLORS = { verde: '#10B981', azul: '#3B82F6', amarillo: '#F59E0B', rojo: '#EF4444' };
const SEM_LABELS = {
  verde: 'Libre · sin reserva',
  azul: 'Reserva por confirmar',
  amarillo: 'Alquiler en curso',
  rojo: '⚠ Alquiler vencido'
};

function fmtCountdown(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = String(Math.floor(s / 3600)).padStart(2, '0');
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const sec = String(s % 60).padStart(2, '0');
  return `${h}:${m}:${sec}`;
}

/* Actualiza la pastilla semáforo de la tarjeta y el cronómetro de alquiler */
function updateSemaforo(card, info, estado) {
  const sem = info && info.semaforo;
  const box = card.querySelector('[data-semaforo]');
  if (!box) return;
  const dot = box.querySelector('[data-semaforo-dot]');
  const label = box.querySelector('[data-semaforo-label]');
  if (!dot || !label) return;

  // El foco se LEE desde la base (tabla semaforo_focos), así que se
  // muestra aunque el Arduino esté offline. Solo se oculta si no hay dato.
  if (!sem || !sem.luz) {
    box.classList.add('d-none');
    dot.style.background = '#CBD5E1';
    label.textContent = 'Sin señal';
    clearInterval(box._semTimer);
    return;
  }

  box.classList.remove('d-none');
  const luz = sem.luz;
  dot.style.background = SEM_COLORS[luz] || '#64748B';

  // En alquiler: cronómetro de cuenta regresiva hasta que venza
  if (luz === 'amarillo' && sem.fin) {
    const finMs = Date.parse(sem.fin);
    const tick = () => {
      label.textContent = `${SEM_LABELS[luz]} · Restan ${fmtCountdown(finMs - Date.now())}`;
    };
    tick();
    clearInterval(box._semTimer);
    box._semTimer = setInterval(tick, 1000);
  } else {
    clearInterval(box._semTimer);
    // Modo manual: usar directamente el detalle que llega de la base
    if (sem.tipo === 'manual') {
      label.textContent = sem.detalle || (SEM_LABELS[luz] || luz);
    } else {
      label.textContent = sem.detalle && sem.detalle !== 'Sin reservas activas'
        ? `${SEM_LABELS[luz] || luz} · ${sem.detalle}`
        : (SEM_LABELS[luz] || luz);
    }
  }
}

/* --- Cronómetros iniciales (desde el render del servidor) --- */
function startElapsedTimers() {
  document.querySelectorAll('[data-elapsed]').forEach((el) => {
    const since = Number(el.dataset.liveSince) || Date.now();
    el.textContent = `En línea ${fmtElapsed(since)}`;
    setInterval(() => {
      el.textContent = `En línea ${fmtElapsed(Number(el.dataset.liveSince) || Date.now())}`;
    }, 1000);
  });
}

/* --- Actualiza una tarjeta según el estado que devuelve la API --- */
function updateModuleCard(card, info) {
  const estado = info ? info.estado : 'apagado';
  const cls = STATUS_CLASSES[estado] || 'warn';

  const pill = card.querySelector('.status-pill');
  const label = pill ? pill.querySelector('[data-status-label]') : null;
  if (pill) {
    pill.className = `status-pill ${cls}`;
    if (label) label.textContent = estado.charAt(0).toUpperCase() + estado.slice(1);
  }

  let elapsed = card.querySelector('[data-elapsed]');
  const heartbeatMs = info && info.ultimo_heartbeat
    ? Date.parse(info.ultimo_heartbeat)
    : null;

  if (estado === 'conectado' || estado === 'esperando') {
    if (!elapsed) {
      elapsed = document.createElement('span');
      elapsed.className = 't-elapsed mt-2 d-block';
      elapsed.setAttribute('data-elapsed', '');
      card.appendChild(elapsed);
    }
    if (heartbeatMs) elapsed.dataset.liveSince = heartbeatMs;
    elapsed.textContent = `En línea ${fmtElapsed(Number(elapsed.dataset.liveSince) || Date.now())}`;
    if (!elapsed._timer) {
      elapsed._timer = setInterval(() => {
        elapsed.textContent = `En línea ${fmtElapsed(Number(elapsed.dataset.liveSince) || Date.now())}`;
      }, 1000);
    }
  } else if (elapsed) {
    elapsed.remove();
  }

  updateSemaforo(card, info, estado);
}

/* --- Fetch del estado global de todos los módulos --- */
function refreshEsp(cacheMode) {
  fetch('/api/esp', { cache: cacheMode || 'no-store' })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((datos) => {
      document.querySelectorAll('[data-esp-status][data-codigo]').forEach((card) => {
        const info = (datos || {})[card.dataset.codigo];
        updateModuleCard(card, info);
      });
    })
    .catch(() => {
      // Si el API no responde (BD caída), marcar offline suave.
      document.querySelectorAll('[data-esp-status]').forEach((card) => {
        updateModuleCard(card, { estado: 'offline' });
      });
    });
}

/* Equalizer (barrita de latencia) para módulos vivos */
function animateEqualizer() {
  document.querySelectorAll('[data-eq]').forEach((group) => {
    group.querySelectorAll('.eq-bar').forEach((bar, i) => {
      bar.style.animationDelay = `${[0, 220, 440][i % 3]}ms`;
      bar.classList.add('live');
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  startElapsedTimers();
  animateEqualizer();
  refreshEsp();
  setInterval(refreshEsp, ESP_REFRESH_MS);
});