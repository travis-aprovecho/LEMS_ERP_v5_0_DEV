/**
 * bom.js — BOM Editor page
 * Depends on: lems-core.js (showToast, apiFetch), Sortable
 *
 * Data bridge: reads from #bom-tree-container data-* attributes.
 * Template sets:
 *   data-parent-id   (part_id of selected assembly, or empty string)
 *   data-add-to      (pre-fill child search on +⋈ quick-add, or empty string)
 */

'use strict';

/* ── Bootstrap from DOM ──────────────────────────────────────────────────────*/
const _treeEl   = document.getElementById('bom-tree-container');
const PARENT_ID = _treeEl?.dataset.parentId  || null;
const ADD_TO    = _treeEl?.dataset.addTo     || null;

/* ── Assembly filter + localStorage ─────────────────────────────────────────*/
const BOM_KEY = 'lems-bom-last';

function filterAsm() {
  const q   = document.getElementById('asm-search').value.toLowerCase();
  const cat = document.getElementById('asm-cat-filter').value;
  document.querySelectorAll('.assembly-item').forEach(el => {
    const matchQ   = el.dataset.name.includes(q);
    const matchCat = !cat || el.dataset.cat === cat;
    el.style.display = (matchQ && matchCat) ? '' : 'none';
  });
  try { localStorage.setItem(BOM_KEY + '-cat', cat); } catch (e) {}
}
document.getElementById('asm-search').addEventListener('input', filterAsm);

// Restore last category filter
(function () {
  try {
    const saved = localStorage.getItem(BOM_KEY + '-cat');
    if (saved) {
      const sel = document.getElementById('asm-cat-filter');
      if (sel) { sel.value = saved; filterAsm(); }
    }
  } catch (e) {}
})();

function selectAssembly(id) {
  try { localStorage.setItem(BOM_KEY, id); } catch (e) {}
  location.href = `/bom?part_id=${encodeURIComponent(id)}`;
}

// Remember last selected assembly when landing with no part_id
if (!PARENT_ID) {
  try {
    const last   = localStorage.getItem(BOM_KEY);
    const exists = last && document.querySelector(`.assembly-item[data-pid="${CSS.escape(last)}"]`);
    if (exists) {
      location.replace(`/bom?part_id=${encodeURIComponent(last)}`);
    } else if (last) {
      localStorage.removeItem(BOM_KEY);   // stale — clear to stop redirect loop
    }
  } catch (e) {}
}

/* ── Part search dropdown ────────────────────────────────────────────────────*/
let _searchTimer;

async function searchChildParts(q) {
  clearTimeout(_searchTimer);
  const dd = document.getElementById('part-dropdown');
  if (!q || q.length < 2) { dd.classList.remove('open'); return; }
  _searchTimer = setTimeout(async () => {
    const res   = await fetch(`/api/parts/search?q=${encodeURIComponent(q)}`);
    const parts = await res.json();
    dd.innerHTML = parts.length
      ? parts.map(p =>
          `<div class="part-dropdown-item"
                data-pid="${escapeHtml(p.part_id)}"
                data-desc="${escapeHtml(p.plain_desc || '')}"
                onmousedown="handleDropdownSelect(this)">
            <div class="pid">${escapeHtml(p.part_id)}</div>
            <div class="pdesc">${escapeHtml(p.plain_desc || '—')}
              <span style="color:var(--accent);font-family:'IBM Plex Mono',monospace">
                $${p.unit_cost.toFixed(2)}</span></div>
          </div>`).join('')
      : '<div class="part-dropdown-item muted small">No results</div>';
    dd.classList.add('open');
  }, 200);
}

function handleDropdownSelect(el) {
  selectChildPart(el.dataset.pid, el.dataset.desc || '');
}

function selectChildPart(id, desc) {
  document.getElementById('child-search').value  = `${id} — ${desc}`;
  document.getElementById('child-id-val').value  = id;
  document.getElementById('part-dropdown').classList.remove('open');
  document.getElementById('child-qty').focus();
}

document.addEventListener('mousedown', e => {
  if (!e.target.closest('.part-search-wrap'))
    document.getElementById('part-dropdown').classList.remove('open');
});

/* ── BOM mutations ───────────────────────────────────────────────────────────*/
async function addComponent() {
  const childId = document.getElementById('child-id-val').value;
  const qty     = document.getElementById('child-qty').value;
  if (!childId) { showToast('Select a part first', 'error'); return; }
  const fd = new FormData();
  fd.append('parent_id', PARENT_ID); fd.append('child_id', childId); fd.append('qty', qty);
  const res = await apiFetch('/bom/add', fd);
  if (res.ok) { showToast('Added — costs updated'); location.reload(); }
  else showToast(res.msg, 'error');
}

async function updateQty(parentId, childId, qty) {
  const fd = new FormData();
  fd.append('parent_id', parentId); fd.append('child_id', childId); fd.append('qty', qty);
  const res = await apiFetch('/bom/update-qty', fd);
  if (res.ok) { showToast('Qty updated — costs updated'); location.reload(); }
  else showToast(res.msg, 'error');
}

async function updateChildLabor(partId, hrs) {
  const fd = new FormData();
  fd.append('part_id', partId); fd.append('labor_hrs', hrs);
  const res = await apiFetch('/bom/update-labor', fd);
  if (res.ok) showToast('Labor updated');
  else showToast(res.msg, 'error');
}

async function saveLabor() {
  const hrs = document.getElementById('labor-hrs-input').value;
  const fd  = new FormData();
  fd.append('part_id', PARENT_ID); fd.append('labor_hrs', hrs);
  const res = await apiFetch('/bom/update-labor', fd);
  if (res.ok) showToast('Labor saved — costs updated');
  else showToast(res.msg, 'error');
}

async function removeComponent(parentId, childId) {
  if (!confirm(`Remove ${childId}?`)) return;
  const fd = new FormData();
  fd.append('parent_id', parentId); fd.append('child_id', childId);
  const res = await apiFetch('/bom/remove', fd);
  if (res.ok) location.reload();
  else showToast(res.msg, 'error');
}

async function rollupThis(reload = true) {
  const fd = new FormData();
  fd.append('labor_rate', 25);
  const res = await apiFetch('/bom/rollup-all', fd);
  if (res.ok) {
    showToast('Costs rolled up');
    if (reload) location.reload();
  } else showToast(res.msg, 'error');
}

/* ── Drag-drop reorder ───────────────────────────────────────────────────────*/
const tbody = document.getElementById('bom-tbody');
if (tbody && typeof Sortable !== 'undefined') {
  Sortable.create(tbody, {
    handle: '.drag-handle', animation: 150,
    ghostClass: 'sortable-ghost', chosenClass: 'sortable-chosen',
    onEnd: async () => {
      const order = [...tbody.querySelectorAll('tr[data-child-id]')]
        .map(r => r.dataset.childId);
      const fd = new FormData();
      fd.append('parent_id', PARENT_ID);
      fd.append('order', JSON.stringify(order));
      const res = await apiFetch('/bom/reorder', fd);
      if (res.ok) showToast('Order saved');
      else showToast(res.msg, 'error');
    },
  });
}

/* ── BOM tree (fetched) ──────────────────────────────────────────────────────*/
function renderTree(node, container) {
  const hasKids = node.children?.length > 0;
  const row     = document.createElement('div');
  row.className = 'bom-node' + (node.optional ? ' optional' : '');
  if (node.optional)
    row.style.background = 'color-mix(in srgb, var(--amber2) 10%, transparent)';

  const toggle = document.createElement('span');
  toggle.className = 'bom-toggle';
  toggle.textContent = hasKids ? '▶' : ' ';
  row.appendChild(toggle);

  const badge = document.createElement('span');
  badge.className   = `badge badge-${node.type}`;
  badge.textContent = node.type;
  row.appendChild(badge);

  const pid = document.createElement('a');
  pid.className       = 'bom-part-id';
  pid.textContent     = node.part_id;
  pid.style.textDecoration = 'none';
  if (['ASSY', 'FAB'].includes(node.type)) {
    pid.href        = `/bom?part_id=${encodeURIComponent(node.part_id)}`;
    pid.style.color = 'var(--blue)';
  } else {
    pid.href        = `/parts/${encodeURIComponent(node.part_id)}/edit`;
    pid.style.color = 'var(--text2)';
  }
  row.appendChild(pid);

  const desc = document.createElement('span');
  desc.className  = 'bom-desc';
  desc.textContent = node.plain_desc || '';
  if (node.optional) {
    const ob = document.createElement('span');
    ob.className  = 'optional-badge';
    ob.textContent = 'OPTIONAL';
    desc.appendChild(ob);
  }
  row.appendChild(desc);

  const qty = document.createElement('span');
  qty.className   = 'bom-qty';
  qty.textContent = node.depth > 0 ? `×${node.bom_qty}` : '';
  row.appendChild(qty);

  const labor = document.createElement('span');
  labor.className   = 'bom-labor';
  labor.textContent = node.labor_hrs > 0
    ? `${parseFloat(node.labor_hrs).toFixed(2)}h` : '';
  row.appendChild(labor);

  const cost = document.createElement('span');
  cost.className   = 'bom-cost';
  cost.textContent = node.unit_cost > 0
    ? `$${parseFloat(node.unit_cost).toFixed(2)}` : '—';
  row.appendChild(cost);

  container.appendChild(row);

  if (hasKids) {
    const cw = document.createElement('div');
    cw.className    = 'bom-children';
    cw.style.display = 'none';
    node.children.forEach(c => renderTree(c, cw));
    container.appendChild(cw);
    toggle.addEventListener('click', e => {
      e.stopPropagation();
      const open = cw.style.display !== 'none';
      cw.style.display  = open ? 'none' : 'block';
      toggle.textContent = open ? '▶' : '▼';
    });
  }
}

function expandAll() {
  document.querySelectorAll('.bom-children').forEach(el => el.style.display = 'block');
  document.querySelectorAll('.bom-toggle').forEach(el => {
    if (el.textContent.trim()) el.textContent = '▼';
  });
}

function collapseAll() {
  document.querySelectorAll('.bom-children').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.bom-toggle').forEach(el => {
    if (el.textContent.trim()) el.textContent = '▶';
  });
}

// Fetch tree from API instead of embedding in page HTML
async function loadTree() {
  if (!PARENT_ID || !_treeEl) return;
  _treeEl.innerHTML =
    '<div class="muted small" style="padding:16px 0">Loading tree…</div>';
  try {
    const res  = await fetch(`/bom/tree/${encodeURIComponent(PARENT_ID)}`);
    const data = await res.json();
    _treeEl.innerHTML = '';
    if (data && data.part_id) {
      renderTree(data, _treeEl);
      expandAll();
    } else {
      _treeEl.innerHTML =
        '<div class="muted small" style="padding:12px 0">No BOM data.</div>';
    }
  } catch (e) {
    _treeEl.innerHTML =
      '<div class="alert alert-error">Failed to load BOM tree.</div>';
  }
}

/* ── Quick-add pre-fill (arriving via +⋈ from parts list) ───────────────────*/
if (ADD_TO && PARENT_ID) {
  document.getElementById('child-search').value = ADD_TO;
  searchChildParts(ADD_TO);
  document.getElementById('child-search').scrollIntoView({ behavior: 'smooth', block: 'center' });
  document.getElementById('child-search').focus();
}

/* ── Init ────────────────────────────────────────────────────────────────────*/
loadTree();
