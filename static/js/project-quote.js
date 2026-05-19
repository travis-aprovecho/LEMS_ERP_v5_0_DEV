/**
 * project-quote.js — Quote Builder page
 * Depends on: lems-core.js (showToast, apiFetch)
 *
 * Data bridge: reads constants from the <form> element's data-* attributes.
 * Template sets:
 *   data-project-id, data-mat-cost, data-labor-hrs,
 *   data-line-disc, data-other-markup, data-other-nomark
 */

'use strict';

/* ── Bootstrap constants from DOM ────────────────────────────────────────────*/
const _form         = document.querySelector('form[data-project-id]');
const PROJECT_ID    = _form?.dataset.projectId    || '';

/* ── View toggle ─────────────────────────────────────────────────────────────*/
function toggleView(v) {
  document.getElementById('view-internal').style.display = v === 'internal' ? '' : 'none';
  document.getElementById('view-proforma').style.display = v === 'proforma'  ? '' : 'none';
  document.getElementById('btn-internal').className =
    'btn btn-sm ' + (v === 'internal' ? 'btn-primary' : 'btn-secondary');
  document.getElementById('btn-proforma').className =
    'btn btn-sm ' + (v === 'proforma'  ? 'btn-primary' : 'btn-secondary');
}

/* ── Live totals recalc — SSOT: all math runs in calculations.py ─────────────
 * recalcTotals() debounces 300 ms, then POSTs current form values to the
 * /quote/preview endpoint.  The server returns JSON; we only update the DOM.
 * No financial math lives in this file.
 * ─────────────────────────────────────────────────────────────────────────── */
let _recalcTimer = null;

function recalcTotals() {
  clearTimeout(_recalcTimer);
  _recalcTimer = setTimeout(_doRecalc, 300);
}

async function _doRecalc() {
  const form = document.querySelector('form[data-project-id]');
  if (!form) return;

  let t;
  try {
    const res = await fetch(`/projects/${PROJECT_ID}/quote/preview`, {
      method: 'POST',
      body:   new FormData(form),
    });
    if (!res.ok) return;
    t = await res.json();
  } catch (e) {
    console.warn('recalcTotals preview failed:', e);
    return;
  }

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const fmt = v => '$' + Number(v).toFixed(2);

  // ── Waterfall rows ─────────────────────────────────────────────────────────
  set('sc-mat-burdened',       fmt(t.mat_burdened));
  set('sc-mat-burdened2',      fmt(t.mat_burdened));
  set('sc-labor-cost',         fmt(t.labor_cost));
  set('wf-markupable',         fmt(t.markupable));
  set('display-markup-amount', fmt(t.markup_amount));
  set('wf-marked-up',          fmt(t.markupable + t.markup_amount));
  set('wf-labor',              fmt(t.labor_cost));
  set('display-pre-discount',  fmt(t.pre_discount));

  // ── Line item discount row (show/hide based on live total) ─────────────────
  const lineDiscRow = document.getElementById('wf-line-disc-row');
  const lineDiscEl  = document.getElementById('wf-line-disc');
  if (lineDiscRow && lineDiscEl) {
    if (t.total_item_disc > 0) {
      lineDiscRow.style.display = '';
      lineDiscEl.textContent    = '−$' + Number(t.total_item_disc).toFixed(2);
    } else {
      lineDiscRow.style.display = 'none';
    }
  }

  // ── Global discount ────────────────────────────────────────────────────────
  const discEl = document.getElementById('wf-global-disc');
  if (discEl) discEl.textContent = t.overall_discount > 0
    ? '−$' + Number(t.overall_discount).toFixed(2) : '—';

  // ── Final quoted price ─────────────────────────────────────────────────────
  ['display-quoted', 'display-quoted2'].forEach(id => set(id, fmt(t.quoted_total)));
  set('display-total-cost', fmt(t.total_internal));

  // ── Gross margin (colour-coded) ────────────────────────────────────────────
  const gm = Number(t.gross_margin_pct);
  const gmColor = gm >= 15 ? 'var(--accent)' : gm >= 0 ? 'var(--amber)' : 'var(--red)';
  ['display-margin', 'sc-margin'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = gm.toFixed(1) + '%'; el.style.color = gmColor; }
  });

  // ── Top stat cards ─────────────────────────────────────────────────────────
  set('sc-quoted',         fmt(t.quoted_total));
  set('sc-total-internal', fmt(t.total_internal));
}


/* ── Freeze / unfreeze / bump version ────────────────────────────────────────*/
async function freezeQuote() {
  if (!confirm(
    'Lock in current BOM costs?\n\n' +
    "The material cost and labor hours will be saved as a snapshot and won't " +
    'change even if part costs are updated later.'
  )) return;
  const res = await apiFetch(`/projects/${PROJECT_ID}/quote/freeze`, new FormData());
  if (res.ok) { showToast('Costs frozen ✓'); setTimeout(() => location.reload(), 800); }
  else showToast(res.msg, 'error');
}

async function unfreezeQuote() {
  if (!confirm('Unfreeze costs?\n\nThe quote will use live BOM values going forward.')) return;
  const res = await apiFetch(`/projects/${PROJECT_ID}/quote/unfreeze`, new FormData());
  if (res.ok) { showToast('Costs unfrozen'); setTimeout(() => location.reload(), 800); }
  else showToast(res.msg, 'error');
}

async function bumpVersion() {
  if (!confirm(
    'Increment the quote version number?\n\n' +
    'Do this each time you send a revised quote to the customer.'
  )) return;
  const res = await apiFetch(`/projects/${PROJECT_ID}/quote/bump-version`, new FormData());
  if (res.ok) {
    showToast(`Now ${res.version ? 'v' + res.version : 'updated'}`);
    setTimeout(() => location.reload(), 800);
  } else showToast(res.msg, 'error');
}
