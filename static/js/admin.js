/**
 * admin.js — Admin / Import page
 * Depends on: lems-core.js (showToast, escapeHtml)
 */

'use strict';

let selectedFile = null;
let masterFile   = null;
let _flagsData   = null;

const EXT_MAP = {
  '.csv':  { endpoint: '/admin/import-csv',  label: 'CSV backup' },
  '.db':   { endpoint: '/admin/import-db',   label: 'SQLite database' },
  '.xlsx': { endpoint: '/admin/import-xlsx', label: 'Excel workbook' },
};

function getExt(name) {
  return name.slice(name.lastIndexOf('.')).toLowerCase();
}

/* ── Standard import ─────────────────────────────────────────────────────────*/
function fileSelected(input) { selectedFile = input.files[0]; _onFile(); }

function handleDrop(e) {
  e.preventDefault();
  const dz = document.getElementById('drop-zone');
  dz.style.borderColor = 'var(--border2)';
  dz.style.background  = '';
  selectedFile = e.dataTransfer.files[0];
  _onFile();
}

function _onFile() {
  if (!selectedFile) return;
  const ext  = getExt(selectedFile.name);
  const info = EXT_MAP[ext];
  document.getElementById('drop-filename').textContent       = selectedFile.name;
  document.getElementById('import-btn').disabled             = !info;
  document.getElementById('import-type-note').textContent    =
    info ? `Detected: ${info.label}` : 'Unsupported file type';
  if (!info) showToast('Please use a .csv, .db, or .xlsx file', 'error');
}

async function doImport() {
  if (!selectedFile) return;
  const ext  = getExt(selectedFile.name);
  const info = EXT_MAP[ext];
  if (!info) return;
  const btn = document.getElementById('import-btn');
  btn.textContent = 'Importing…';
  btn.disabled    = true;
  const fd = new FormData();
  fd.append('file', selectedFile);
  try {
    const res  = await fetch(info.endpoint, { method: 'POST', body: fd });
    const data = await res.json();
    const r    = data.results || {};
    document.getElementById('import-results').style.display = 'block';
    document.getElementById('import-stats').innerHTML =
      `<span style="color:var(--accent)">✓</span> Parts: <strong>${r.parts || 0}</strong><br>
       <span style="color:var(--accent)">✓</span> BOM rows: <strong>${r.bom || 0}</strong><br>
       <span style="color:var(--accent)">✓</span> Projects: <strong>${r.projects || 0}</strong><br>
       <span style="color:var(--accent)">✓</span> Project items: <strong>${r.items || 0}</strong>`;
    if (r.errors?.length) {
      document.getElementById('import-errors').innerHTML =
        `<div class="alert alert-error"><strong>${r.errors.length} warning(s):</strong><br>` +
        r.errors.slice(0, 10)
          .map(e => `<div class="mono small" style="margin-top:4px">${escapeHtml(e)}</div>`)
          .join('') +
        (r.errors.length > 10
          ? `<div class="muted small">…and ${r.errors.length - 10} more</div>`
          : '') + '</div>';
    } else {
      document.getElementById('import-errors').innerHTML =
        '<div class="alert alert-success">No errors — import clean.</div>';
    }
    showToast(`Imported — ${r.parts || 0} parts, ${r.bom || 0} BOM rows`);
    loadFlags();
  } catch (e) {
    showToast('Import failed: ' + escapeHtml(e.message), 'error');
  }
  btn.textContent = 'Import';
  btn.disabled    = false;
}

/* ── Master data replace ─────────────────────────────────────────────────────*/
function masterFileSelected(input) { masterFile = input.files[0]; _onMasterFile(); }

function handleMasterDrop(e) {
  e.preventDefault();
  document.getElementById('master-drop-zone').style.background = '';
  masterFile = e.dataTransfer.files[0];
  _onMasterFile();
}

function _onMasterFile() {
  if (!masterFile) return;
  const ext = getExt(masterFile.name);
  document.getElementById('master-filename').textContent = masterFile.name;
  if (ext !== '.csv') {
    document.getElementById('master-btn').disabled           = true;
    document.getElementById('master-type-note').textContent  = 'Master replace requires a .csv file';
    showToast('Master replace requires a .csv file', 'error');
  } else {
    document.getElementById('master-btn').disabled           = false;
    document.getElementById('master-type-note').textContent  =
      'Ready — will wipe all parts & BOM before loading';
  }
}

async function doMasterImport() {
  if (!masterFile) return;
  if (!confirm(
    '⚠ WIPE & REPLACE\n\n' +
    'This will permanently delete ALL existing parts and BOM rows, ' +
    'then load the new master file.\n\n' +
    'Projects and project items are not affected.\n\n' +
    'Are you sure you want to continue?'
  )) return;

  const btn = document.getElementById('master-btn');
  btn.textContent = 'Replacing…';
  btn.disabled    = true;
  const fd = new FormData();
  fd.append('file', masterFile);
  try {
    const res  = await fetch('/admin/import-master', { method: 'POST', body: fd });
    const data = await res.json();
    const r    = data.results || {};
    document.getElementById('master-results').style.display = 'block';
    document.getElementById('master-stats').innerHTML =
      `<span style="color:var(--red,#c0392b)">✗</span> Removed: ` +
      `<strong>${r.deleted_parts || 0} parts, ${r.deleted_bom || 0} BOM rows</strong><br>` +
      `<span style="color:var(--accent)">✓</span> Loaded: ` +
      `<strong>${r.parts || 0} parts, ${r.bom || 0} BOM rows</strong>`;
    if (r.errors?.length) {
      document.getElementById('master-errors').innerHTML =
        `<div class="alert alert-error"><strong>${r.errors.length} warning(s):</strong><br>` +
        r.errors.slice(0, 10)
          .map(e => `<div class="mono small" style="margin-top:4px">${escapeHtml(e)}</div>`)
          .join('') +
        (r.errors.length > 10
          ? `<div class="muted small">…and ${r.errors.length - 10} more</div>`
          : '') + '</div>';
    } else {
      document.getElementById('master-errors').innerHTML =
        '<div class="alert alert-success">No errors — master data loaded clean.</div>';
    }
    showToast(`Master replace done — ${r.parts || 0} parts loaded`);
    loadFlags();
  } catch (e) {
    showToast('Master replace failed: ' + escapeHtml(e.message), 'error');
  }
  btn.textContent = '⚠ Wipe & Replace';
  btn.disabled    = false;
}

/* ── Flags ───────────────────────────────────────────────────────────────────*/
const FLAG_GROUPS = [
  { key: 'obsolete_bom',     label: 'Obsolete parts in active BOMs',     sev: 'error',
    desc: 'These parts are marked OBSOLETE but still referenced in BOM relationships. Remove or replace them.' },
  { key: 'empty_bom',        label: 'FAB/ASSY with no BOM children',     sev: 'error',
    desc: 'These assemblies have no components defined. Their cost will be $0 until children are added.' },
  { key: 'zero_cost',        label: 'Zero-cost purchased parts (PRT/RAW)', sev: 'error',
    desc: 'These parts have no unit cost set. They will silently contribute $0 to any BOM rollup.' },
  { key: 'orphaned',         label: 'PRT/RAW not used in any BOM',       sev: 'warn',
    desc: 'These parts exist in the master list but are not referenced in any assembly. May be unused or need cleanup.' },
  { key: 'missing_supplier', label: 'PRT/RAW without supplier (has cost)', sev: 'warn',
    desc: 'These costed parts have no supplier recorded. Add supplier info for procurement traceability.' },
  { key: 'missing_desc',     label: 'Parts missing descriptions',         sev: 'info',
    desc: 'These parts have no plain_desc. Descriptions are used in search, print, and pick lists.' },
];

async function loadFlags() {
  const container = document.getElementById('flags-container');
  container.innerHTML = '<div class="muted small" style="padding:8px 0">Loading…</div>';
  try {
    const data  = await fetch('/api/flags').then(r => r.json());
    _flagsData  = data;
    const total = data.total;
    document.getElementById('flags-total').textContent =
      total === 0 ? '✓ all clear' : `${total} issue${total !== 1 ? 's' : ''}`;

    if (total === 0) {
      container.innerHTML =
        `<div style="text-align:center;padding:32px;color:var(--accent)">
          <div style="font-size:28px;margin-bottom:10px">✓</div>
          <div style="font-size:14px">No issues found — database is clean.</div>
        </div>`;
      return;
    }

    const SHOW = 12;
    let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">';
    for (const grp of FLAG_GROUPS) {
      const rows  = data.flags[grp.key] || [];
      if (!rows.length) continue;
      const color = grp.sev === 'error' ? 'var(--red)' : grp.sev === 'warn' ? 'var(--amber)' : 'var(--blue)';
      const bg    = grp.sev === 'error' ? 'var(--badge-obs-bg)' : grp.sev === 'warn' ? 'var(--amber2)' : 'var(--badge-assy-bg)';
      html +=
        `<div style="background:${bg};border:1px solid ${color};border-radius:8px;padding:14px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="color:${color};font-size:12px;font-weight:600">${grp.label}</span>
            <span style="color:#000;font-family:'IBM Plex Mono',monospace;font-size:11px;
                         margin-left:auto;background:${color};padding:1px 6px;border-radius:3px;
                         opacity:0.85">${rows.length}</span>
          </div>
          <div class="muted small" style="margin-bottom:8px;font-size:11px">${grp.desc}</div>
          <div id="flag-list-${grp.key}" style="font-family:'IBM Plex Mono',monospace;font-size:11px;max-height:160px;overflow-y:auto">`;
      rows.forEach((r, idx) => {
        const link = r.parent_id
          ? `/bom?part_id=${encodeURIComponent(r.parent_id)}`
          : (['FAB', 'ASSY'].includes(r.type))
            ? `/bom?part_id=${encodeURIComponent(r.part_id)}`
            : `/parts/${encodeURIComponent(r.part_id)}/edit`;
        const hidden = idx >= SHOW ? ' class="flag-overflow" style="display:none"' : '';
        html +=
          `<div${hidden} style="padding:2px 0;border-bottom:1px solid rgba(128,128,128,0.15);
                                display:flex;gap:6px;align-items:center">
            <a href="${link}" style="color:${color};text-decoration:none;flex:1;
                                     overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
               title="${escapeHtml(r.part_id)}">${escapeHtml(r.part_id)}</a>
            <span style="opacity:0.6;font-size:10px">${escapeHtml(r.category || r.type || '')}</span>
          </div>`;
      });
      if (rows.length > SHOW) {
        html +=
          `<div style="padding-top:5px">
            <button onclick="expandFlags('${escapeHtml(grp.key)}',this)"
                    style="background:none;border:none;color:${color};font-size:10px;
                           cursor:pointer;padding:0;font-family:inherit">
              ▶ Show all ${rows.length} items
            </button>
          </div>`;
      }
      html += `</div></div>`;
    }
    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML =
      `<div class="alert alert-error">Failed to load flags: ${escapeHtml(e.message)}</div>`;
  }
}

function expandFlags(key, btn) {
  const list = document.getElementById('flag-list-' + key);
  if (!list) return;
  list.querySelectorAll('.flag-overflow').forEach(el => el.style.display = '');
  list.style.maxHeight = 'none';
  btn.parentElement.style.display = 'none';
}

/* ── Flags export / print ────────────────────────────────────────────────────*/
const FLAG_LABELS = {
  obsolete_bom:     'Obsolete in BOM',
  empty_bom:        'Empty BOM',
  zero_cost:        'Zero Cost',
  orphaned:         'Orphaned',
  missing_supplier: 'No Supplier',
  missing_desc:     'No Description',
};

function printFlags() {
  if (!_flagsData) { showToast('Load flags first', 'error'); return; }
  const win = window.open('', '_blank');
  win.document.write(
    `<!DOCTYPE html><html><head><title>LEMS ERP — System Flags</title>
    <style>body{font-family:Arial,sans-serif;font-size:10pt;padding:20px}
    h1{font-size:14pt;margin-bottom:4px}h2{font-size:11pt;margin:16px 0 4px;color:#333}
    table{width:100%;border-collapse:collapse;margin-bottom:12px}
    th{background:#ddd;padding:4px 8px;text-align:left;font-size:9pt}
    td{padding:3px 8px;border-bottom:1px solid #eee;font-size:9pt}
    .err{color:#c03030}.warn{color:#a06000}.info{color:#1a6aaa}
    </style></head><body>
    <h1>LEMS ERP — System Flags &amp; Warnings</h1>
    <p style="color:#555;font-size:9pt">Generated ${new Date().toLocaleString()}</p>`
  );
  const sevClass = {
    obsolete_bom: 'err', empty_bom: 'err', zero_cost: 'err',
    orphaned: 'warn', missing_supplier: 'warn', missing_desc: 'info',
  };
  for (const [key, rows] of Object.entries(_flagsData.flags)) {
    if (!rows.length) continue;
    win.document.write(
      `<h2 class="${sevClass[key] || 'info'}">${FLAG_LABELS[key] || key} (${rows.length})</h2>
       <table><tr><th>Part ID</th><th>Type</th><th>Category</th><th>Description</th></tr>`
    );
    rows.forEach(r => {
      win.document.write(
        `<tr>
          <td>${escapeHtml(r.part_id || '')}</td>
          <td>${escapeHtml(r.type || '')}</td>
          <td>${escapeHtml(r.category || '')}</td>
          <td>${escapeHtml(r.plain_desc || '')}</td>
        </tr>`
      );
    });
    win.document.write('</table>');
  }
  win.document.write('</body></html>');
  win.document.close();
  win.print();
}

function exportFlagsCSV() {
  if (!_flagsData) { showToast('Load flags first', 'error'); return; }
  let csv = 'Flag Type,Part ID,Type,Category,Description\n';
  for (const [key, rows] of Object.entries(_flagsData.flags)) {
    rows.forEach(r => {
      const desc = (r.plain_desc || '').replace(/"/g, '""');
      csv += `"${FLAG_LABELS[key] || key}","${r.part_id || ''}","${r.type || ''}","${r.category || ''}","${desc}"\n`;
    });
  }
  const blob = new Blob([csv], { type: 'text/csv' });
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `lems_flags_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  showToast('Flags exported to CSV');
}

/* ── Init ────────────────────────────────────────────────────────────────────*/
loadFlags();
