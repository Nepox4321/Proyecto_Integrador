/* ============================================================
   AutoNova · main.js
   Interactividad general: filtros de catálogo, cálculo de
   presupuesto en checkout, mensajes flash y toggles.
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
  applyActiveNav();
  initCatalogFilters();
  initCheckoutBudget();
  initBackToTop();
});

// Marca el enlace activo según la ruta (data-active en el nav)
function applyActiveNav() {
  const current = document.body.dataset.page || '';
  document.querySelectorAll('.nav-link[data-active]').forEach((link) => {
    if (link.dataset.active === current) link.classList.add('active');
  });
}

// --- Catálogo: filtrar por categoría y búsqueda ---
function initCatalogFilters() {
  const input = document.getElementById('searchVehicle');
  const category = document.getElementById('filterCategory');
  if (!input && !category) return;

  const apply = () => {
    const q = (input ? input.value : '').toLowerCase().trim();
    const cat = category ? category.value : 'all';
    document.querySelectorAll('[data-category]').forEach((card) => {
      const matchCat = cat === 'all' || card.dataset.category === cat;
      const matchQ = !q || (card.dataset.title || '').toLowerCase().includes(q);
      card.classList.toggle('d-none', !(matchCat && matchQ));
    });
  };

  if (input) input.addEventListener('input', apply);
  if (category) category.addEventListener('change', apply);
}

// --- Checkout: recalcular total por días ---
function initCheckoutBudget() {
  const from = document.getElementById('fechaInicio');
  const to = document.getElementById('fechaFin');
  const rateEl = document.getElementById('tarifaDia');
  const totalEl = document.getElementById('totalReserva');
  const diasEl = document.getElementById('diasReserva');
  if (!from || !to || !rateEl || !totalEl) return;

  const formatUSD = (v) => '$' + Number(v).toLocaleString('en-US');

  const calc = () => {
    const a = new Date(from.value || '');
    const b = new Date(to.value || '');
    const rate = Number(rateEl.value || rateEl.dataset.value || 0);
    let dias = 0;
    if (a instanceof Date && b instanceof Date && b > a) {
      dias = Math.round((b - a) / (1000 * 60 * 60 * 24));
    }
    const total = dias * rate;
    if (diasEl) diasEl.textContent = `${dias} día(s)`;
    if (totalEl) totalEl.textContent = formatUS(total) || '—';
  };

  const formatUS = (v) => (v ? `$${v.toLocaleString('en-US')}` : '');
  from.addEventListener('change', calc);
  to.addEventListener('change', calc);
  calc();
}

// --- Botón "volver arriba" ---
function initBackToTop() {
  const btn = document.getElementById('backToTop');
  if (!btn) return;
  btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}