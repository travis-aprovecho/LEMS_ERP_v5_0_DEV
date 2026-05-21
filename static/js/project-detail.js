/**
 * project-detail.js — Project Order Sheet page
 * Depends on: lems-core.js (showToast, apiFetch, escapeHtml)
 *
 * Data bridge: PROJECT_ID is read from the first [data-project] element,
 * which already exists on .editable-meta cells in the template.
 * No HTML changes needed.
 */

'use strict';

/* ── Bootstrap PROJECT_ID from DOM ──────────────────────────────────────────*/
// Note: the old inline script had two separate constants for the same project ID value.
// Both are replaced by a single PROJECT_ID read from the DOM below.
const PROJECT_ID = document.querySelector('[data-project]')?.dataset.project ?? '';

/* ── Editable metadata cells ─────────────────────────────────────────────────*/
document.querySelectorAll('.editable-meta').forEach(cell => {
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
    fd.append('field', cell.dataset.field);
    fd.append('value', val);
    const res = await apiFetch(`/projects/${PROJECT_ID}/inline-edit`, fd);
    if (res.ok) {
      cell.dataset.orig = val;
      showToast('Saved');
      if (cell.dataset.field === 'labor_rate' || cell.dataset.field === 'status') {
        setTimeout(() => location.reload(), 400);
      }
    } else {
      cell.textContent = cell.dataset.orig;
      showToast(res.msg, 'error');
    }
  });
});

async function saveMetaSelect(projId, field, val) {
  const fd = new FormData();
  fd.append('field', field);
  fd.append('value', val);
  const res = await apiFetch(`/projects/${projId}/inline-edit`, fd);
  if (res.ok) showToast('Saved');
  else showToast(res.msg, 'error');
}

/* ── Part search dropdown ────────────────────────────────────────────────────*/
let _searchTimer;

async function searchParts(q) {
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
  selectPart(el.dataset.pid, el.dataset.desc || '');
}

function selectPart(id, desc) {
  document.getElementById('pi-search').value  = `${id} — ${desc}`;
  document.getElementById('pi-part-id').value = id;
  document.getElementById('part-dropdown').classList.remove('open');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.part-search-wrap'))
    document.getElementById('part-dropdown').classList.remove('open');
});

/* ── Order sheet mutations ───────────────────────────────────────────────────*/
async function addItem() {
  const partId = document.getElementById('pi-part-id').value;
  const qty    = document.getElementById('pi-qty').value;
  const itype  = document.getElementById('pi-type').value;
  if (!partId) { showToast('Select a part first', 'error'); return; }
  const fd = new FormData();
  fd.append('part_id', partId);
  fd.append('qty', qty);
  const res = await apiFetch(`/projects/${PROJECT_ID}/add-item`, fd);
  if (res.ok) {
    if (itype !== 'ADDITIONAL' && res.item_id) {
      const fd2 = new FormData();
      fd2.append('item_id', res.item_id);
      fd2.append('item_type', itype);
      await apiFetch('/projects/item/set-type', fd2);
    }
    location.reload();
  } else showToast(res.msg, 'error');
}

async function setItemType(itemId, itype) {
  const fd = new FormData();
  fd.append('item_id', itemId);
  fd.append('item_type', itype);
  const res = await apiFetch('/projects/item/set-type', fd);
  if (res.ok) { showToast(`→ ${itype}`); location.reload(); }
  else showToast(res.msg, 'error');
}

async function updateItemQty(itemId, qty) {
  const fd = new FormData();
  fd.append('item_id', itemId);
  fd.append('qty', qty);
  const res = await apiFetch('/projects/item/update', fd);
  if (res.ok) showToast('Qty updated');
  else showToast(res.msg, 'error');
}

async function removeItem(itemId) {
  if (!confirm('Remove this item?')) return;
  const fd = new FormData();
  fd.append('item_id', itemId);
  const res = await apiFetch('/projects/item/delete', fd);
  if (res.ok) location.reload();
  else showToast(res.msg, 'error');
}

async function updateItemDiscount(itemId, pct, flat) {
  const fd = new FormData();
  fd.append('item_id', itemId);
  if (pct  !== null) fd.append('discount_pct',  pct  || 0);
  if (flat !== null) fd.append('discount_flat', flat || 0);
  const res = await apiFetch('/projects/item/update', fd);
  if (res.ok) {
    const val = pct !== null ? pct : flat;
    showToast(val ? 'Discount updated' : 'Discount cleared');
    setTimeout(() => location.reload(), 400);
  } else showToast(res.msg, 'error');
}

async function cloneProject() {
  const newId = prompt('New project ID for clone:', PROJECT_ID + '_COPY');
  if (!newId) return;
  const fd = new FormData();
  fd.append('new_id', newId);
  const res = await apiFetch(`/projects/${PROJECT_ID}/clone`, fd);
  if (res.ok) {
    showToast('Project cloned — opening…');
    setTimeout(() => location.href = `/projects/${encodeURIComponent(res.new_id || newId)}`, 600);
  } else showToast(res.msg, 'error');
}

/* ── Exploded BOM modal ───────────────────────────────────────────────────────*/
function _renderModalTree(node, container, depth) {
  if (!node || !node.part_id) return;
  const hasKids = node.children?.length > 0;

  const row = document.createElement('div');
  row.style.cssText = `display:flex;align-items:center;gap:6px;padding:4px 12px 4px ${12 + depth * 18}px;
    border-bottom:1px solid var(--border);min-height:28px;`;
  if (depth === 0) row.style.background = 'var(--bg2)';

  // Toggle
  const tog = document.createElement('span');
  tog.style.cssText = 'width:12px;flex-shrink:0;cursor:pointer;color:var(--text3);font-size:10px;user-select:none';
  tog.textContent = hasKids ? '▶' : '';
  row.appendChild(tog);

  // Type badge
  const badge = document.createElement('span');
  badge.className   = `badge badge-${node.type}`;
  badge.textContent = node.type;
  badge.style.fontSize = '9px';
  row.appendChild(badge);

  // Part ID link
  const pid = document.createElement('a');
  pid.href   = `/parts/${encodeURIComponent(node.part_id)}/edit`;
  pid.target = '_blank';
  pid.style.cssText = `font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:${['ASSY','FAB'].includes(node.type) ? 'var(--blue)' : 'var(--text2)'};
    text-decoration:none;flex-shrink:0`;
  pid.textContent = node.part_id;
  row.appendChild(pid);

  // Description
  const desc = document.createElement('span');
  desc.style.cssText = 'font-size:12px;color:var(--text1);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  desc.textContent   = node.plain_desc || '';
  if (node.optional) {
    const ob = document.createElement('span');
    ob.style.cssText  = 'font-size:9px;color:var(--amber);margin-left:4px;font-weight:600';
    ob.textContent    = 'OPT';
    desc.appendChild(ob);
  }
  row.appendChild(desc);

  // Qty
  if (depth > 0) {
    const qty = document.createElement('span');
    qty.style.cssText = `font-family:'IBM Plex Mono',monospace;font-size:11px;
      color:var(--text2);flex-shrink:0;min-width:40px;text-align:right`;
    qty.textContent = `×${node.bom_qty}`;
    row.appendChild(qty);
  }

  // Labor
  if (node.labor_hrs > 0) {
    const lbr = document.createElement('span');
    lbr.style.cssText = `font-family:'IBM Plex Mono',monospace;font-size:10px;
      color:var(--amber);flex-shrink:0;min-width:44px;text-align:right`;
    lbr.textContent = `${parseFloat(node.labor_hrs).toFixed(2)}h`;
    row.appendChild(lbr);
  }

  // Cost
  const cost = document.createElement('span');
  cost.style.cssText = `font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--accent);flex-shrink:0;min-width:70px;text-align:right`;
  cost.textContent = node.unit_cost > 0 ? `$${parseFloat(node.unit_cost).toFixed(2)}` : '—';
  row.appendChild(cost);

  container.appendChild(row);

  if (hasKids) {
    const childWrap = document.createElement('div');
    childWrap.style.display = 'none';
    node.children.forEach(c => _renderModalTree(c, childWrap, depth + 1));
    container.appendChild(childWrap);

    tog.addEventListener('click', () => {
      const open = childWrap.style.display !== 'none';
      childWrap.style.display = open ? 'none' : 'block';
      tog.textContent = open ? '▶' : '▼';
    });
    // Auto-expand first level
    if (depth === 0) { childWrap.style.display = 'block'; tog.textContent = '▼'; }
  }
}

function _countTreeNodes(node) {
  if (!node) return 0;
  return 1 + (node.children || []).reduce((s, c) => s + _countTreeNodes(c), 0);
}

async function openBomModal(partId, desc) {
  const backdrop = document.getElementById('bom-modal-backdrop');
  const body     = document.getElementById('bom-modal-body');
  const pid      = document.getElementById('bom-modal-pid');
  const title    = document.getElementById('bom-modal-title');
  const count    = document.getElementById('bom-modal-count');
  const link     = document.getElementById('bom-modal-link');

  title.textContent = desc || 'BOM Tree';
  pid.textContent   = partId;
  link.href         = `/bom?part_id=${encodeURIComponent(partId)}`;
  body.innerHTML    = '<div style="padding:40px;text-align:center;color:var(--text2)">Loading…</div>';
  count.textContent = '';
  backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';

  try {
    const res  = await fetch(`/bom/tree/${encodeURIComponent(partId)}`);
    const tree = await res.json();

    if (!tree || !tree.part_id) {
      body.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text2)">No BOM data.</div>';
      return;
    }

    // Header row labels
    const hdr = document.createElement('div');
    hdr.style.cssText = `display:flex;align-items:center;gap:6px;padding:5px 12px;
      background:var(--bg3);border-bottom:2px solid var(--border2);position:sticky;top:0;z-index:1`;
    hdr.innerHTML = `
      <span style="width:12px;flex-shrink:0"></span>
      <span style="width:32px;flex-shrink:0;font-size:9px;font-weight:600;letter-spacing:.1em;
                   text-transform:uppercase;color:var(--text3)">TYPE</span>
      <span style="font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
                   color:var(--text3);flex-shrink:0;min-width:180px">PART ID</span>
      <span style="font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
                   color:var(--text3);flex:1">DESCRIPTION</span>
      <span style="font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
                   color:var(--text3);min-width:40px;text-align:right">QTY</span>
      <span style="font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
                   color:var(--amber);min-width:44px;text-align:right">LABOR</span>
      <span style="font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
                   color:var(--accent);min-width:70px;text-align:right">COST</span>`;

    const treeContainer = document.createElement('div');
    _renderModalTree(tree, treeContainer, 0);

    body.innerHTML = '';
    body.appendChild(hdr);
    body.appendChild(treeContainer);

    const nodeCount = _countTreeNodes(tree) - 1; // exclude root
    count.textContent = `${nodeCount} component${nodeCount !== 1 ? 's' : ''}`;

  } catch (e) {
    body.innerHTML = `<div style="padding:40px;text-align:center;color:var(--red)">
      Failed to load BOM: ${escapeHtml(e.message)}</div>`;
  }
}

function closeBomModal() {
  document.getElementById('bom-modal-backdrop').classList.remove('open');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeBomModal();
});


function recalcOrderTotals() {
  // BOM material cost is static — comes from server render, can't change without reload.
  // Only custom items change live, so we sum those from the live input values.
  let customCost = 0, customLbr = 0;
  document.querySelectorAll('#other-items-body tr[data-oi-id]').forEach(tr => {
    customCost += parseFloat(tr.querySelector('input[onchange*="\'cost\'"]')?.value)       || 0;
    customLbr  += parseFloat(tr.querySelector('input[onchange*="\'labor_hrs\'"]')?.value)  || 0;
  });

  // Read the server-rendered BOM totals from the already-populated cells
  const bomMatText  = (document.getElementById('ot-bom-mat')?.textContent  || '$0').replace(/[$,]/g, '');
  const bomLbrText  = (document.getElementById('ot-bom-lbr')?.textContent  || '0').replace(' hrs', '');
  const bomMat      = parseFloat(bomMatText)  || 0;
  const bomLbr      = parseFloat(bomLbrText)  || 0;

  const totalMat = bomMat + customCost;
  const totalLbr = bomLbr + customLbr;

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  set('ot-custom-cost', '$' + customCost.toFixed(2));
  set('ot-custom-lbr',  customLbr.toFixed(2) + ' hrs');
  set('ot-total-mat',   '$' + totalMat.toFixed(2));
  set('ot-total-lbr',   totalLbr.toFixed(2) + ' hrs');

  // Show custom rows if there are items
  const hasCustom = document.querySelectorAll('#other-items-body tr[data-oi-id]').length > 0;
  ['ot-custom-cost-row','ot-custom-lbr-row'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = hasCustom ? '' : 'none';
  });
}


async function addOtherItem() {
  const res = await apiFetch(`/projects/${PROJECT_ID}/other-items/add`, new FormData());
  if (res.ok) {
    showToast('Row added ✓', 'success', 1200);
    const empty = document.getElementById('other-items-empty');
    if (empty) empty.remove();
    const tbody = document.getElementById('other-items-body');
    const tr    = document.createElement('tr');
    tr.dataset.oiId = res.id;
    // Safe: res.id is a DB integer, no user data in these values
    tr.innerHTML =
      `<td><input type="text" value="" style="width:100%"
             onchange="updateOtherItem(${res.id},'description',this.value)"></td>
       <td><input type="number" value="" step="0.01" min="0" placeholder="0"
             style="width:90px;text-align:right"
             onchange="updateOtherItem(${res.id},'cost',this.value)"></td>
       <td><input type="number" value="" step="0.1" min="0" placeholder="0"
             style="width:70px;text-align:right"
             onchange="updateOtherItem(${res.id},'labor_hrs',this.value)"></td>
       <td style="text-align:center">
         <input type="checkbox" style="width:14px;height:14px;accent-color:var(--amber)"
                onchange="updateOtherItem(${res.id},'apply_markup',this.checked?1:0)"></td>
       <td><input type="text" value="" style="width:60px"
             onchange="updateOtherItem(${res.id},'box_num',this.value)"></td>
       <td><input type="number" value="" step="0.1" min="0" max="100" placeholder="%"
             style="width:100%;text-align:right"
             onchange="updateOtherItem(${res.id},'discount_pct',this.value)"></td>
       <td><input type="number" value="" step="0.01" min="0" placeholder="$"
             style="width:100%;text-align:right"
             onchange="updateOtherItem(${res.id},'discount_flat',this.value)"></td>
       <td><button onclick="deleteOtherItem(${res.id},this)"
                   class="btn btn-ghost btn-xs" style="color:var(--red)">✕</button></td>`;
    tbody.appendChild(tr);
  } else showToast(res.msg, 'error');
}

async function updateOtherItem(id, field, value) {
  const fd = new FormData();
  fd.append('item_id', id);
  fd.append('field', field);
  fd.append('value', value);
  const res = await apiFetch('/projects/other-item/update', fd);
  if (res.ok) { showToast('Saved ✓', 'success', 1200); recalcOrderTotals(); }
  else showToast(res.msg, 'error');
}

async function deleteOtherItem(id, btn) {
  const fd = new FormData();
  fd.append('item_id', id);
  const res = await apiFetch('/projects/other-item/delete', fd);
  if (res.ok) {
    btn.closest('tr').remove();
    if (!document.querySelector('#other-items-body tr[data-oi-id]')) {
      document.getElementById('other-items-body').innerHTML =
        '<tr id="other-items-empty"><td colspan="9" class="muted text-center" ' +
        'style="padding:20px">No custom items yet — click "+ Add Row" to add one.</td></tr>';
    }
    recalcOrderTotals();
  } else showToast(res.msg, 'error');
}

async function updateItemBox(itemId, boxNum) {
  const fd = new FormData();
  fd.append('item_id', itemId);
  fd.append('box_num', boxNum);
  const res = await apiFetch('/projects/item/update', fd);
  if (res.ok) showToast('Box updated');
  else showToast(res.msg, 'error');
}

/* ── Packing ─────────────────────────────────────────────────────────────────*/
function recalcPalletWeights() {
  const boxWeights = {};
  document.querySelectorAll('#boxes-table tbody tr').forEach(tr => {
    const pal = tr.querySelector('.b-pal')?.value.trim() || '';
    const wt  = parseFloat(tr.querySelector('.b-wt')?.value) || 0;
    if (pal) boxWeights[pal] = (boxWeights[pal] || 0) + wt;
  });
  document.querySelectorAll('#pallets-table tbody tr').forEach(tr => {
    const palNum  = tr.querySelector('.p-num')?.value.trim() || '';
    const tarewt  = parseFloat(tr.querySelector('.p-wt')?.value) || 0;
    const grossEl = tr.querySelector('.pallet-gross');
    if (grossEl) grossEl.textContent =
      (tarewt + (boxWeights[palNum] || 0)).toFixed(1) + ' lbs';
  });
}

function addBoxRow() {
  const tbody   = document.querySelector('#boxes-table tbody');
  const nums    = Array.from(tbody.querySelectorAll('.b-num'))
                       .map(el => parseInt(el.value) || 0);
  const nextNum = Math.max(0, ...nums) + 1;
  const tr      = document.createElement('tr');
  // Safe: nextNum is a computed integer, no user data
  tr.innerHTML =
    `<td><input type="text" class="b-num" value="${nextNum}"></td>
     <td><input type="number" class="b-wt" value="0" oninput="recalcPalletWeights()"></td>
     <td><input type="text" class="b-pal" oninput="recalcPalletWeights()"></td>
     <td style="text-align:center">
       <button onclick="this.parentElement.parentElement.remove();recalcPalletWeights()"
               class="btn btn-ghost btn-xs text-red">✕</button></td>`;
  tbody.appendChild(tr);
}

function addPalletRow() {
  const tbody   = document.querySelector('#pallets-table tbody');
  const nums    = Array.from(tbody.querySelectorAll('.p-num'))
                       .map(el => parseInt(el.value) || 0);
  const nextNum = Math.max(0, ...nums) + 1;
  const tr      = document.createElement('tr');
  tr.innerHTML =
    `<td><input type="text" class="p-num" value="${nextNum}"></td>
     <td><input type="number" class="p-wt" value="0" oninput="recalcPalletWeights()"></td>
     <td><input type="text" class="p-dim"></td>
     <td class="pallet-gross" style="font-weight:600;color:var(--accent);vertical-align:middle">0.0 lbs</td>
     <td style="text-align:center">
       <button onclick="this.parentElement.parentElement.remove();recalcPalletWeights()"
               class="btn btn-ghost btn-xs text-red">✕</button></td>`;
  tbody.appendChild(tr);
}

async function savePacking() {
  const boxes = Array.from(document.querySelectorAll('#boxes-table tbody tr')).map(tr => ({
    box_num:    tr.querySelector('.b-num').value.trim(),
    weight:     parseFloat(tr.querySelector('.b-wt').value) || 0,
    pallet_num: tr.querySelector('.b-pal').value.trim(),
  })).filter(b => b.box_num);

  const pallets = Array.from(document.querySelectorAll('#pallets-table tbody tr')).map(tr => ({
    pallet_num: tr.querySelector('.p-num').value.trim(),
    weight:     parseFloat(tr.querySelector('.p-wt').value) || 0,
    dimensions: tr.querySelector('.p-dim').value.trim(),
  })).filter(p => p.pallet_num);

  const res  = await fetch(`/projects/${PROJECT_ID}/packing/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ boxes, pallets }),
  });
  const data = await res.json();
  if (data.ok) showToast('Packing data saved');
  else showToast(data.msg || 'Error saving packing data', 'error');
}

/* ── Optional items panel ────────────────────────────────────────────────────*/
function toggleOptPanel() {
  const body  = document.getElementById('opt-suggest-body');
  const caret = document.getElementById('opt-caret');
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (caret) caret.classList.toggle('open', !open);
}

document.addEventListener('DOMContentLoaded', () => {
  if (sessionStorage.getItem('optPanelOpen')) {
    sessionStorage.removeItem('optPanelOpen');
    const body  = document.getElementById('opt-suggest-body');
    const caret = document.getElementById('opt-caret');
    if (body)  body.style.display = 'block';
    if (caret) caret.classList.add('open');
  }
});

async function addOptional(partId, typeSelId, qtyInputId, cardId) {
  const itype = document.getElementById(typeSelId)?.value || 'OPTION';
  const qty   = parseFloat(document.getElementById(qtyInputId)?.value) || 1;
  const fd    = new FormData();
  fd.append('part_id', partId);
  fd.append('qty', qty);
  const res = await apiFetch(`/projects/${PROJECT_ID}/add-item`, fd);
  if (!res.ok) { showToast(res.msg, 'error'); return; }
  if (itype !== 'ADDITIONAL' && res.item_id) {
    const fd2 = new FormData();
    fd2.append('item_id', res.item_id);
    fd2.append('item_type', itype);
    await apiFetch('/projects/item/set-type', fd2);
  }
  sessionStorage.setItem('optPanelOpen', '1');
  const card = document.getElementById(cardId);
  if (card) card.classList.add('added-opt');
  showToast(`${partId} added as ${itype}`);
  setTimeout(() => location.reload(), 800);
}

/* ── Project Attachments Modal ──────────────────────────────────────────────*/
async function showProjectAttachments(projId) {
  const backdrop = document.getElementById('attachments-modal-backdrop');
  const body     = document.getElementById('attachments-modal-body');
  
  body.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text2)">Loading…</div>';
  backdrop.classList.add('open');
  
  try {
    const res  = await fetch(`/api/projects/${encodeURIComponent(projId)}/attachments`);
    const data = await res.json();
    
    if (!data || !data.length) {
      body.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text2)">No attachments found in this project\'s BOM.</div>';
      return;
    }
    
    body.innerHTML = `<table class="data-table">
      <thead><tr><th style="width:150px">Part ID</th><th>Filename</th><th style="text-align:right; width:80px;">Size</th><th style="text-align:right; width:120px;">Uploaded</th></tr></thead>
      <tbody>
        ${data.map(a => `
          <tr>
            <td class="mono small"><a href="/parts/${encodeURIComponent(a.part_id)}/edit" target="_blank">${escapeHtml(a.part_id)}</a></td>
            <td><a href="/attachments/${a.id}" target="_blank">${escapeHtml(a.original_filename)}</a></td>
            <td class="small text-right">${(a.size_bytes / 1024).toFixed(1)} KB</td>
            <td class="small text-right">${a.uploaded_at.split(' ')[0]}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:40px;text-align:center;color:var(--red)">Failed to load attachments.</div>`;
  }
}
