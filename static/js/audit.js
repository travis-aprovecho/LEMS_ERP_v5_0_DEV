/**
 * audit.js — Audit log page
 * Depends on: lems-core.js
 */

'use strict';

// Expand truncated old_val / new_val on row click
document.querySelectorAll('#audit-table tbody tr').forEach(tr => {
  tr.style.cursor = 'pointer';
  tr.addEventListener('click', () => {
    const cells = tr.querySelectorAll('td:nth-child(7), td:nth-child(8)');
    cells.forEach(td => {
      if (td.style.whiteSpace === 'normal') {
        td.style.whiteSpace = 'nowrap';
        td.style.overflow   = 'hidden';
      } else {
        td.style.whiteSpace = 'normal';
        td.style.overflow   = 'visible';
      }
    });
  });
});

// Keyboard shortcut: / focuses entity_id search
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    document.querySelector('[name="entity_id"]')?.focus();
  }
});
