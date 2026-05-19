/**
 * parts.js — Parts Master page
 * Depends on: lems-core.js (showToast, apiFetch)
 */

'use strict';

/* ── Part actions ────────────────────────────────────────────────────────────*/
async function setStatus(partId, status) {
  const fd = new FormData();
  fd.append('part_id', partId);
  fd.append('field', 'status');
  fd.append('value', status);
  const res = await apiFetch('/parts/inline-edit', fd);
  if (res.ok) showToast(`Status → ${status}`);
  else showToast(res.msg, 'error');
}

async function deletePart(partId) {
  if (!confirm(`Delete part:\n${partId}\n\nThis cannot be undone.`)) return;
  const fd  = new FormData();
  const res = await apiFetch(`/parts/${encodeURIComponent(partId)}/delete`, fd);
  if (res.ok) { showToast('Part deleted'); location.reload(); }
  else showToast(res.msg, 'error');
}

/* ── Filter persistence ──────────────────────────────────────────────────────*/
(function initFilterPersistence() {
  const form = document.getElementById('filter-form');
  if (!form) return;
  const KEY       = 'lems-parts-filters';
  const urlParams = new URLSearchParams(window.location.search);
  const hasUrl    = urlParams.has('search') || urlParams.has('type_f') || urlParams.has('cat_f');

  if (!hasUrl) {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
      if (saved.search) { const el = form.querySelector('[name=search]');  if (el) el.value = saved.search; }
      if (saved.type_f) { const el = form.querySelector('[name=type_f]');  if (el) el.value = saved.type_f; }
      if (saved.cat_f)  { const el = form.querySelector('[name=cat_f]');   if (el) el.value = saved.cat_f;  }
      if (saved.search || saved.type_f || saved.cat_f) form.submit();
    } catch (e) {}
  }

  form.addEventListener('submit', () => {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        search: form.querySelector('[name=search]')?.value  || '',
        type_f: form.querySelector('[name=type_f]')?.value  || '',
        cat_f:  form.querySelector('[name=cat_f]')?.value   || '',
      }));
    } catch (e) {}
  });

  const clearBtn = form.querySelector('a[href="/parts"]');
  if (clearBtn) clearBtn.addEventListener('click', () => {
    try { localStorage.removeItem(KEY); } catch (e) {}
  });
})();

/* ── Column sort ─────────────────────────────────────────────────────────────*/
let _sortCol = -1, _sortAsc = true;

document.querySelectorAll('th.sortable').forEach(th => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const col = parseInt(th.dataset.col);
    if (_sortCol === col) _sortAsc = !_sortAsc;
    else { _sortCol = col; _sortAsc = true; }

    const tbody = document.querySelector('#parts-table tbody');
    const rows  = [...tbody.querySelectorAll('tr')];
    rows.sort((a, b) => {
      const at = a.cells[col]?.textContent.trim().replace(/[$,]/g, '') || '';
      const bt = b.cells[col]?.textContent.trim().replace(/[$,]/g, '') || '';
      const an = parseFloat(at), bn = parseFloat(bt);
      const cmp = (!isNaN(an) && !isNaN(bn))
        ? an - bn
        : at.localeCompare(bt, undefined, { numeric: true });
      return _sortAsc ? cmp : -cmp;
    });
    rows.forEach(r => tbody.appendChild(r));
    document.querySelectorAll('.sort-icon').forEach(s => s.textContent = '↕');
    th.querySelector('.sort-icon').textContent = _sortAsc ? '↑' : '↓';
  });
});
