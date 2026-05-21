/**
 * part-form.js — New / Edit Part form
 * Depends on: lems-core.js (showToast, apiFetch)
 */

'use strict';

/* ── Field-values autocomplete ───────────────────────────────────────────────*/
let _fieldVals = null;

async function loadFieldValues() {
  try {
    const res  = await fetch('/api/parts/field-values');
    _fieldVals = await res.json();
    populateDatalist('dl-base-desc', _fieldVals.base_desc);
    populateDatalist('dl-size-spec', _fieldVals.size_spec);
    populateDatalist('dl-variant',   _fieldVals.variant);
  } catch (e) {}
}

function populateDatalist(id, values) {
  const dl = document.getElementById(id);
  if (!dl) return;
  dl.innerHTML = values.map(v => `<option value="${escapeHtml(v)}">`).join('');
}

function filterDatalist(inputId, datalistId) {
  if (!_fieldVals) return;
  const input = document.getElementById(inputId);
  const dl    = document.getElementById(datalistId);
  if (!input || !dl) return;
  const q   = input.value.toUpperCase();
  const key = inputId === 'fdesc' ? 'base_desc'
            : inputId === 'fsize' ? 'size_spec' : 'variant';
  const filtered = q.length < 1
    ? _fieldVals[key]
    : _fieldVals[key].filter(v => v.toUpperCase().includes(q));
  populateDatalist(datalistId, filtered);
}

/* ── Part ID preview ─────────────────────────────────────────────────────────*/
function updatePreview() {
  const t = document.getElementById('ftype')?.value  || '';
  const c = document.getElementById('fcat')?.value   || '';
  const d = (document.getElementById('fdesc')?.value || '').toUpperCase().replace(/[^A-Z0-9\-\/\.]/g, '');
  const s = (document.getElementById('fsize')?.value || '').toUpperCase().replace(/[^A-Z0-9\-\/\.]/g, '');
  const v = (document.getElementById('fvar')?.value  || '').toUpperCase().replace(/[^A-Z0-9\-\/\.]/g, '');
  const segs = [t, c, d];
  if (s) segs.push(s);
  if (v) segs.push(v);
  const el = document.getElementById('id-preview');
  if (el) el.textContent = segs.filter(Boolean).join('-') || '—';
  const note = document.getElementById('unit-cost-note');
  if (note) note.textContent = ['PRT', 'RAW'].includes(t) ? '— auto from pkg' : '';
}

/* ── Unit cost recalc ────────────────────────────────────────────────────────*/
function recalcUnit() {
  const t  = document.getElementById('ftype')?.value || '';
  if (!['PRT', 'RAW'].includes(t)) return;
  const ps = parseFloat(document.getElementById('fpkgsize')?.value) || 1;
  const pc = parseFloat(document.getElementById('fpkgcost')?.value) || 0;
  const el = document.getElementById('funitcost');
  if (el) el.value = ps > 0 ? (pc / ps).toFixed(6) : '0';
}

function recalcAlt() {
  const ps = parseFloat(document.getElementById('fpkgsize2')?.value) || 1;
  const pc = parseFloat(document.getElementById('fpkgcost2')?.value) || 0;
  const el = document.getElementById('funitcost2');
  if (el) el.value = ps > 0 ? (pc / ps).toFixed(6) : '0';
}

/* ── Alt supplier toggle ─────────────────────────────────────────────────────*/
function toggleAltCost() {
  const active = document.getElementById('use-alt-cb')?.checked;
  const note   = document.getElementById('alt-active-note');
  if (note) note.style.display = active ? 'block' : 'none';
}

/* ── Delete part ─────────────────────────────────────────────────────────────*/
async function deletePart(partId) {
  if (!confirm(`Delete ${partId}?\nThis cannot be undone.`)) return;
  const fd  = new FormData();
  const res = await apiFetch(`/parts/${encodeURIComponent(partId)}/delete`, fd);
  if (res.ok) location.href = '/parts?msg=Part+deleted';
  else showToast(res.msg, 'error');
}

/* ── Clear all fields ────────────────────────────────────────────────────────*/
function clearAllFields() {
  if (!confirm('Clear all fields?')) return;
  ['ftype', 'fcat'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.selectedIndex = 0;
  });
  ['fdesc', 'fsize', 'fvar'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  ['supplier', 'brand_mfg', 'supplier_pn', 'plain_desc'].forEach(name => {
    const el = document.querySelector(`[name="${name}"]`);
    if (el) el.value = '';
  });
  [['fpkgsize','1'], ['fpkgcost','0'], ['funitcost','0'],
   ['[name=labor_hrs]','0'], ['[name=qty_on_hand]','0']].forEach(([sel, def]) => {
    const el = sel.startsWith('[') ? document.querySelector(sel) : document.getElementById(sel);
    if (el) el.value = def;
  });
  const uom = document.getElementById('fuom');
  if (uom) uom.selectedIndex = 0;
  const status = document.querySelector('[name=status]');
  if (status) status.value = 'ACTIVE';
  updatePreview();
  recalcUnit();
}

/* ── Auto-uppercase ID fields ────────────────────────────────────────────────*/
['fdesc', 'fsize', 'fvar'].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('input', () => {
    const p = el.selectionStart;
    el.value = el.value.toUpperCase();
    el.setSelectionRange(p, p);
  });
});

/* ── Init ────────────────────────────────────────────────────────────────────*/
document.addEventListener('DOMContentLoaded', loadFieldValues);
updatePreview();
toggleAltCost();

/* ── Attachments ─────────────────────────────────────────────────────────────*/
async function loadAttachments(partId) {
  if (!partId || partId === '—') return;
  const list = document.getElementById('attachments-list');
  if (!list) return;
  
  try {
    const res = await fetch(`/api/parts/${encodeURIComponent(partId)}/attachments`);
    const data = await res.json();
    if (!data.length) {
      list.innerHTML = '<div class="muted small">No attachments found.</div>';
      return;
    }
    
    list.innerHTML = `<table class="data-table" style="margin-top: 8px;">
      <thead><tr><th>Filename</th><th style="text-align:right; width:60px;">Size</th><th style="width:40px;"></th></tr></thead>
      <tbody>
        ${data.map(a => `
          <tr>
            <td><a href="/attachments/${a.id}" target="_blank">${escapeHtml(a.original_filename)}</a></td>
            <td class="small text-right">${(a.size_bytes / 1024).toFixed(1)} KB</td>
            <td style="text-align:center;">
              <button type="button" class="btn btn-ghost btn-sm" style="color:var(--danger); padding:2px 6px;" onclick="deleteAttachment('${a.id}', '${partId}')" title="Delete">✕</button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;
  } catch (e) {
    list.innerHTML = '<div class="alert-error">Error loading attachments.</div>';
  }
}

async function uploadAttachment(partId, inputEl) {
  if (!inputEl.files || !inputEl.files[0]) return;
  const file = inputEl.files[0];
  if (file.size > 50 * 1024 * 1024) {
    showToast('File too large (max 50MB)', 'error');
    inputEl.value = '';
    return;
  }
  
  const fd = new FormData();
  fd.append('file', file);
  
  const list = document.getElementById('attachments-list');
  if (list) list.innerHTML = '<div class="muted small">Uploading...</div>';
  
  const res = await apiFetch(`/api/parts/${encodeURIComponent(partId)}/attachments`, fd);
  inputEl.value = '';
  if (res.ok) {
    showToast('File uploaded', 'success');
    loadAttachments(partId);
  } else {
    showToast(res.msg || 'Upload failed', 'error');
    loadAttachments(partId);
  }
}

async function deleteAttachment(attId, partId) {
  if (!confirm('Delete this attachment?')) return;
  const res = await apiFetch(`/api/attachments/${encodeURIComponent(attId)}`, null, 'DELETE');
  if (res.ok) {
    showToast('Deleted', 'success');
    loadAttachments(partId);
  } else {
    showToast(res.msg || 'Delete failed', 'error');
  }
}
