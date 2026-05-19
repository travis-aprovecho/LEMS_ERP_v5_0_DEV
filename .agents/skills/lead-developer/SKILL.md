---
name: Lead Developer
description: The Lead Developer protocol for the LEMS ERP system, governing architectural patterns and strict development rules.
---
# LEMS ERP — Lead Developer Protocol

## Stack & File Map

This is a **FastAPI + Jinja2 SSR application** backed by **SQLite with WAL mode**. There is no frontend framework, no bundler, and no build step. Understanding the exact role of each file before touching anything is mandatory.

| File | Role |
|---|---|
| `database.py` | All DB access, CRUD, BOM logic, rollup, audit logging. ~2500 lines — read the relevant section header before editing. |
| `calculations.py` | **Single source of truth for all pricing math.** `compute_quote_totals()` is the only place quote math lives. Never duplicate it in JS or routing logic. |
| `utils.py` | Backup logic only. `IDLE_BACKUP_MINUTES` and `KEEP_BACKUPS` are the only config values. |
| `main.py` | FastAPI routes only. No business logic. All writes go through `database.py` functions. All JSON responses use `jresp(ok, msg, **extra)`. |
| `static/js/lems-core.js` | Shared utilities loaded on every page: `escapeHtml()`, `showToast()`, `apiFetch()`, `toggleMode()`, `toggleSidebar()`. Never duplicate these. |
| `static/js/{page}.js` | Page-specific JS. One file per page. Loaded via `{% block extra_js %}`. |
| `static/css/app.css` | Single CSS file. All styling. Dark/light mode via CSS variables. No other stylesheets exist. |
| `templates/base.html` | Defines blocks: `breadcrumb`, `page_title`, `topbar_actions`, `content`, `extra_js`. |

---

## 1. Architecture Rules (Non-Negotiable)

### Layering
- **`database.py`** → data only. Returns `dict`, `list[dict]`, `tuple[bool, str]`, or `Optional[dict]`.
- **`calculations.py`** → pricing math only. Called from routes, never from `database.py`.
- **`main.py`** → routes only. Calls `db.*` and `calculations.*`, passes results to templates.
- **Templates** → rendering only. No business logic in Jinja2. If you need a computed value in a template, compute it in the route and pass it in the context.

### Write Functions Must Log Changes
Every function in `database.py` that mutates data must call `log_change()` or `_diff_log()` inside the same transaction. Pattern:

```python
with get_conn() as conn:
    old = conn.execute("SELECT * FROM parts WHERE part_id=?", (part_id,)).fetchone()
    old_row = dict(old) if old else {}
    # ... perform write ...
    _diff_log(conn, 'part', part_id, old_row, new_data, LOGGED_FIELDS)
```

If the write fails and rolls back, the log entry rolls back with it. Never log after the `with` block.

### Optimistic Locking
Forms handling complex data (like Quotes) must include an `<input type="hidden" name="updated_at" value="{{ quote.updated_at }}">`. The underlying `save_quote` function strictly guards against concurrent saves by checking this timestamp. Never bypass optimistic locking.

### SSOT Server-Side Preview Math
Never write financial calculation logic in JavaScript. Interactive calculation forms (like Quote Builder) must debounce changes and `POST` to a `/preview` route that calls `calculations.py`, and rely on the returned JSON to update the DOM.

### JSON Responses
All POST/API routes return through `jresp()`:
```python
return jresp(True, "Saved.")
return jresp(False, "Part not found.", item_id=new_id)
```
Never construct a raw `JSONResponse({"ok": ..., "msg": ...})` manually.

---

## 2. Database Patterns

### Connection management
Use `get_conn()` as a context manager. It commits on success, rolls back on exception:
```python
with get_conn() as conn:
    conn.execute("UPDATE ...", (...,))
```
Never open a connection outside a `with` block. Never call `conn.commit()` manually.

### Upsert Pattern for Imports
All external data parsing (CSV, XLSX, SQLite merges) must delegate to `_upsert_part_row(conn, row)`. Never use raw `INSERT OR REPLACE INTO parts` statements for imports, as they silently destroy alternate supplier tracking data.

### New columns → add to `_migrate_schema()`
Every new column needs an entry in the `migrations` list in `_migrate_schema()` so existing databases get it on startup:
```python
("parts", "new_col", "ALTER TABLE parts ADD COLUMN new_col TEXT DEFAULT ''"),
```
For new tables use a `CREATE TABLE` entry — see the `change_log` entry as the pattern.

### Rollup integrity
Any function that modifies BOM structure or part cost must call `run_rollup_for_part_and_ancestors(part_id)` after the write so `unit_cost` and `rolled_labor_hrs` stay current. Never skip this — stale rollup values silently corrupt project totals.

### Part type constants
Use the module-level constants — do not hardcode type strings:
```python
PART_TYPES_WITH_BOM    # ('ASSY', 'FAB')
PART_TYPES_STATIC_COST # ('PRT', 'RAW')
ITEM_TYPES             # ('STANDARD', 'OPTION', 'ADDITIONAL', 'DELETED')
```

---

## 3. CSS Rules

### Always use CSS variables — never hardcode colours
```css
/* ✓ correct */
color: var(--accent);
background: var(--bg2);
border: 1px solid var(--border);

/* ✗ wrong */
color: #00c8a0;
background: #1a1e24;
```

### Token reference (most common)
| Token | Purpose |
|---|---|
| `--bg0/1/2/3/4` | Page → card → inset backgrounds (light gets depth from shadow, not colour alone) |
| `--accent` / `--accent2` | Teal — primary interactive colour |
| `--text0/1/2/3` | Body → secondary → muted → disabled text |
| `--border` / `--border2` | Subtle → standard borders |
| `--amber` / `--amber2` | Warnings, labor hours, optional items |
| `--red` / `--red2` | Errors, delete actions, DELETED item type |
| `--blue` / `--blue2` | Info, BOM links, OPTION item type |
| `--shadow` / `--card-shadow` | Elevation. Use `--card-shadow` for cards in light mode. |

### Existing utility classes — check before writing new CSS
- **Cards:** `.card`, `.card-header`
- **Tables:** `.table-wrap`, `th`, `td` (sticky thead built-in)
- **Buttons:** `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.btn-xs`
- **Forms:** `.form-grid`, `.form-grid-3`, `.form-group`, `label`, `input`, `select`, `textarea`
- **Icon buttons:** `.icon-btn`, `.icon-btn.accent`, `.icon-btn.danger`
- **Tooltips:** `[data-tip]` attribute — CSS only, no JS needed
- **Field hints:** `.field-hint` + `.field-hint-icon` + `.field-hint-text`
- **Type badges:** `.badge-ASSY`, `.badge-FAB`, `.badge-PRT`, `.badge-RAW`
- **Layout:** `.grid-2`, `.grid-3`, `.grid-4`, `.flex`, `.gap-*`
- **Typography:** `.mono` (IBM Plex Mono), `.muted`, `.small`, `.text-accent`, `.text-amber`, `.text-red`

### Adding new styles
Add to `app.css` — never inline `<style>` blocks in templates. Place new rules in the relevant section (marked with `/* ── Section ──*/` headers). If the section doesn't exist, add it before the `@media print` block.

---

## 4. JavaScript Rules

### `escapeHtml()` is mandatory for all user data in innerHTML
`escapeHtml()` is defined in `lems-core.js` and available on every page. Any value that originated from user input or the database must be escaped before being written to `innerHTML`:
```js
// ✓ correct
row.innerHTML = `<td>${escapeHtml(part.part_id)}</td><td>${escapeHtml(part.plain_desc)}</td>`;

// ✗ wrong — XSS risk
row.innerHTML = `<td>${part.part_id}</td>`;
```
Static structural HTML (empty state rows, spinners, integer counts) does not need escaping.

### Jinja → JS data bridge: use `data-*` attributes
Never embed Jinja variables directly in `.js` files. Server data needed by JS is placed on a container element in the template:
```html
<!-- template -->
<form data-project-id="{{ project.project_id }}"
      data-mat-cost="{{ mat_cost }}"
      data-labor-hrs="{{ labor_hrs }}">
```
```js
// .js file — reads from DOM, no Jinja syntax
const form      = document.querySelector('form[data-project-id]');
const projectId = form.dataset.projectId;
const matCost   = parseFloat(form.dataset.matCost) || 0;
```
Existing bridge mounting points: `form[data-project-id]` (quote page), `#bom-tree-container[data-parent-id]` (BOM editor), `[data-project]` (order sheet).

### Use `apiFetch()` for all POST calls — never raw `fetch` for mutations
```js
// ✓ correct — uses apiFetch from lems-core.js
const fd = new FormData();
fd.append('part_id', partId);
fd.append('value', newValue);
const res = await apiFetch('/parts/inline-edit', fd);
if (res.ok) showToast('Saved');
else showToast(res.msg, 'error');

// ✗ wrong — duplicates error handling and misses backup trigger
const r = await fetch('/parts/inline-edit', { method: 'POST', body: fd });
```

### Adding a new page script
1. Create `static/js/{page-name}.js`
2. Add at the bottom of the relevant template:
```html
{% block extra_js %}
<script src="/static/js/{page-name}.js"></script>
{% endblock %}
```
3. The file can reference `escapeHtml`, `showToast`, `apiFetch` without importing — they're always available from `lems-core.js`.

### Fetch pattern for async data (not page-server-render)
For data that shouldn't block page render (BOM trees, large lists), use fetch-on-load:
```js
async function loadData() {
  container.innerHTML = '<div class="muted small">Loading…</div>';
  try {
    const res  = await fetch(`/api/endpoint/${encodeURIComponent(id)}`);
    const data = await res.json();
    // render data into container
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}
loadData(); // call at bottom of file, not in DOMContentLoaded
```

---

## 5. Template Rules

### Block structure (base.html)
Every page template must extend base.html and fill the relevant blocks:
```html
{% extends "base.html" %}
{% block breadcrumb %}<a href="/">Home</a> <span class="breadcrumb-sep">›</span> <a href="/parts">Parts</a> <span class="breadcrumb-sep">›</span>{% endblock %}
{% block page_title %}Page Title{% endblock %}

{% block topbar_actions %}
{# Buttons that appear in the top bar, separated from title by a vertical rule #}
<a href="/parts/new" class="btn btn-primary btn-sm">+ New Part</a>
{% endblock %}

{% block content %}
{# Page body #}
{% endblock %}

{% block extra_js %}
<script src="/static/js/page-name.js"></script>
{% endblock %}
```

### No inline `<style>` blocks in templates
All CSS goes in `app.css`. The only exception is one-off layout values (`style="width:140px"`) that are truly not reusable.

### No inline `<script>` blocks in templates
All JS goes in `static/js/`. The only permitted inline script is the FOUC-prevention mode restore in `base.html` — do not add others.

### Displaying flash messages
Pass `msg` and `err` in the route context and display via the standard pattern already in base templates. Do not invent new notification mechanisms.

---

## 6. Route Patterns

### Page routes (GET, returns HTML)
```python
@app.get("/parts/{part_id}/edit", response_class=HTMLResponse)
async def part_edit(request: Request, part_id: str, msg: str = '', err: str = ''):
    part = db.get_part(part_id)
    if not part:
        return RedirectResponse("/parts?err=Not+found", 303)
    return templates.TemplateResponse("part_form.html", {
        "request": request, "part": part, "msg": msg, "err": err,
    })
```

### Action routes (POST, returns JSON via jresp)
```python
@app.post("/parts/{part_id}/delete")
async def part_delete(part_id: str):
    ok, msg = db.delete_part(part_id)
    return jresp(ok, msg)
```

### API routes (GET, returns JSON)
```python
@app.get("/api/parts/search")
async def parts_search(q: str = ''):
    results = db.get_all_parts(search=q)[:20]
    return JSONResponse([dict(p) for p in results])
```

### New routes that need audit logging
The audit trail is written inside `database.py` write functions — routes do not call `log_change()` directly. If you add a new route that mutates data, make sure the underlying `database.py` function calls `log_change()` or `_diff_log()` before merging.

---

## 7. Pre-Commit Checklist

Before outputting any code change:

- [ ] **CSS variables only** — no hardcoded colours or `#hex` values in new CSS
- [ ] **`escapeHtml()` on all user data** in any `innerHTML` assignment
- [ ] **`data-*` bridge** used for any Jinja value needed in a `.js` file — no Jinja syntax in `.js` files
- [ ] **`log_change()` or `_diff_log()` called** inside the transaction for any new write function in `database.py`
- [ ] **`run_rollup_for_part_and_ancestors()`** called after any BOM or cost change
- [ ] **Migration entry added** to `_migrate_schema()` for any new DB column or table
- [ ] **`jresp()`** used for all JSON mutation responses in `main.py`
- [ ] **No business logic in templates** — computed values passed from the route
- [ ] **No duplicate function definitions** — search `database.py` before adding a new function
- [ ] **Error handling** — `try/except` in Python, `try/catch` in JS around all DB calls, fetches, and file operations
- [ ] **`snake_case`** in Python, **`camelCase`** in JS — no exceptions
