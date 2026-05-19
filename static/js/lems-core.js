/**
 * lems-core.js — Shared utilities loaded on every page via base.html
 * Covers: mode toggle, toast notifications, API fetch helper,
 *         inline cell editing, sidebar collapse, flag badge.
 */

'use strict';

/* ── XSS-safe HTML escaping ─────────────────────────────────────────────────*/
function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/* ── Dark / light mode toggle ───────────────────────────────────────────────*/
function toggleMode() {
  const isLight = document.documentElement.classList.toggle('light');
  localStorage.setItem('lems-mode', isLight ? 'light' : 'dark');
  const lbl = document.getElementById('mode-label');
  if (lbl) lbl.textContent = isLight ? 'Light mode' : 'Dark mode';
}

(function initModeLabel() {
  const lbl = document.getElementById('mode-label');
  if (lbl) lbl.textContent =
    document.documentElement.classList.contains('light') ? 'Light mode' : 'Dark mode';
})();

/* ── Toast notifications ────────────────────────────────────────────────────*/
function showToast(msg, type = 'success', duration = 3200) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className   = `toast ${type} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), duration);
}

/* ── API fetch helper ───────────────────────────────────────────────────────*/
async function apiFetch(url, formData) {
  const r = await fetch(url, { method: 'POST', body: formData });
  return r.json();
}

/* ── Sidebar collapse ───────────────────────────────────────────────────────*/
function toggleSidebar() {
  const sb   = document.getElementById('sidebar');
  const btn  = document.getElementById('sidebar-toggle');
  const main = document.querySelector('.main');
  const collapsed = sb.classList.toggle('collapsed');
  document.body.classList.toggle('sidebar-collapsed', collapsed);
  if (btn)  btn.textContent = collapsed ? '▶' : '◀';
  if (main) main.style.marginLeft = collapsed ? '0' : '';
  try { localStorage.setItem('lems-sidebar', collapsed ? '1' : '0'); } catch (e) {}
}

(function initSidebar() {
  try {
    if (localStorage.getItem('lems-sidebar') === '1') {
      const sb   = document.getElementById('sidebar');
      const btn  = document.getElementById('sidebar-toggle');
      const main = document.querySelector('.main');
      if (sb)   sb.classList.add('collapsed');
      if (btn)  btn.textContent = '▶';
      document.body.classList.add('sidebar-collapsed');
      if (main) main.style.marginLeft = '0';
    }
  } catch (e) {}
})();

/* ── DOMContentLoaded init ──────────────────────────────────────────────────*/
document.addEventListener('DOMContentLoaded', () => {

  /* Inline cell edit — parts list (contenteditable td) */
  document.querySelectorAll('td[contenteditable]').forEach(cell => {
    const orig = cell.textContent.trim();
    cell.dataset.orig = orig;

    cell.addEventListener('keydown', e => {
      if (e.key === 'Enter')  { e.preventDefault(); cell.blur(); }
      if (e.key === 'Escape') { cell.textContent = cell.dataset.orig; cell.blur(); }
    });

    cell.addEventListener('blur', async () => {
      const val = cell.textContent.trim();
      if (val === cell.dataset.orig) return;
      const fd = new FormData();
      fd.append('part_id', cell.dataset.partId);
      fd.append('field',   cell.dataset.field);
      fd.append('value',   val);
      const res = await apiFetch('/parts/inline-edit', fd);
      if (res.ok) {
        cell.dataset.orig = val;
        showToast('Saved');
      } else {
        cell.textContent = cell.dataset.orig;
        showToast(res.msg, 'error');
      }
    });
  });

  /* Sidebar flag badge — load count from API */
  fetch('/api/flags')
    .then(r => r.json())
    .then(data => {
      const badge = document.getElementById('nav-flag-badge');
      if (badge && data.total > 0) {
        badge.textContent = data.total;
        badge.style.display = 'inline';
      }
    })
    .catch(() => {});
});
