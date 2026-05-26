# LEMS ERP — Changelog

---

## v5.0.0 — Part Attachments & Cost History

### Part Attachments
- **Local File Storage:** Added the ability to upload and store files (`.pdf`, `.png`, etc.) directly on the local filesystem within an `attachments/` directory.
- **Part Editor Integration:** Added an "Attachments & Drawings" card to the Part Editor UI, allowing users to upload, view, and delete attachments per part.
- **Project Order Sheet Integration:** Added a "📂 Project Attachments" button and modal to the Project detail view. This aggregates all attachments for every part inside the project's current BOM hierarchy.

### Cost History
- **Cost History Tracking:** Cost updates (when `pkg_cost` or `pkg_cost_2` changes) are automatically logged in a `part_cost_history` table.
- **Cost History UI:** Added a modal to the Part Editor showing the chronological history of cost changes (Date, Old Cost, New Cost).

### Inventory Need & Pick List Improvements
- **Project Need Toggle:** Inventory / Count Sheet view now includes a toggle to switch between "Global Need" (across all projects) and "Project Need" (isolated to a specific project).
- **Picked Items Deduction:** The `global_need` calculation now accurately deducts the `picked_qty` of items from active projects to prevent "Need to Order" from artificially inflating.
- **Partial Picking Support:** The Pick List interface now supports partial picking and returning of remaining items.

### Backend Infrastructure
- **Strict Guardrails Audit:** Performed a comprehensive codebase audit to enforce `change_log` logging on all mutating functions and automatic BOM cost rollups after inline edits.

---

## v4.0.2 — Post-Audit Cleanups
_Applied after full codebase review; all 53 tests still passing_

#### Duplicate HTML ID bug (`project_quote.html`)
- **`id="sc-mat-burdened2"`** — the "Burdened Material" display in the BOM Costs block had the same `id` as the stat card. The JS `recalcTotals()` only updated the first match (stat card); the waterfall row stayed stale after a live recalc. Fixed by giving the waterfall copy the correct `id="sc-mat-burdened2"` which was already targeted in `project-quote.js`

#### Stale `quote.other_items` loop removed (`project_quote.html`)
- The pro-forma view iterated `{% for item in quote.other_items if item.show_on_proforma %}` — a loop over the old JSON blob field in `project_quotes` which is always `[]` post-migration to `project_other_items`. Custom items are already rendered above via `quote_line_items`. Dead loop removed; replaced with a clarifying comment

#### `total_internal` now written on quote POST (`main.py` + `database.py`)
- `quote_save()` in `main.py` now sets `data['total_internal'] = totals['total_internal']` alongside `quoted_total` and `gross_margin_pct`
- `save_quote()` in `database.py` now writes `total_internal` in both the INSERT and `ON CONFLICT DO UPDATE SET` clauses
- Previously, `total_internal` was only written on the quote GET route, so the projects list showed a stale internal cost until someone re-visited the quote page

#### `markup_pct` guard consistent with `calculations.py` (`database.py`)
- `save_quote()` now uses an explicit `is not None` check for `markup_pct` instead of `or 0`, matching the guard in `calculations.py` line 35. Functionally equivalent (both produce `0` for an explicit zero), but eliminates the semantic inconsistency

#### Dead JS constants removed (`project-quote.js`)
- Removed `MAT_COST`, `LABOR_HRS`, `TOTAL_LINE_DISC`, `OTHER_MARKUP`, `OTHER_NOMARK` — module-level constants that were never read after `recalcTotals()` was rewritten to delegate all math to the server-side preview endpoint

#### Dead `data-*` attributes removed (`project_quote.html`)
- Removed `data-mat-cost`, `data-labor-hrs`, `data-line-disc`, `data-other-markup`, `data-other-nomark` from the `<form>` tag — these were the data bridge for the old client-side math; none are read by the current `project-quote.js`

#### Duplicate `style=` on gross margin display fixed (`project_quote.html`)
- `<div id="display-margin">` had two separate `style=` attributes; the browser silently dropped the first one (losing `font-size:20px` and `font-weight:700`). Merged into a single attribute so both font and color rules apply

---

## v4.0 — Released

### Phase 1 — Dead code removal & housekeeping

**Removed**
- `compare_boms()` and `/bom/compare` route — template never existed; route 500'd on every visit
- First (incomplete) copy of `explode_bom_flat` — missing `return rows`
- First (incomplete) copy of `get_project_items` — missing `CASE item_type` sort and discount columns
- First (incomplete) copy of `get_project_summary` — missing per-line discount fields
- `_migrate_v23()` — migrations folded into `_migrate_schema()`
- `_migrate_other_items()` monkey-patch — now called directly from `init_db()`
- Module-level `init_db()` call — was causing double init on every server start

**Fixed**
- `save_quote_totals()` bare `except: pass` → `logging.warning()`
- All inline stdlib imports inside function bodies moved to file tops

**Result:** 214 lines removed, zero behaviour changes.

---

### Phase 2 — Performance
_Fixed 10-second LAN page loads_

- WAL mode enabled — prevents "database is locked" on concurrent LAN access
- 4 missing indexes: `bom(child_id)`, `bom(parent_id)`, `project_items(project_id)`, `project_pick_status(project_id)`
- `rolled_labor_hrs` column on `parts` — `run_rollup` now stores it alongside `unit_cost`
- `rollup_all` memoized — shared sub-assemblies rolled up exactly once (O(N))
- All recursive tree functions refactored to pass a single connection — eliminates N+1 per-node connection opens
- `explode_bom_flat` pre-loads full BOM and parts tables into memory before recursing — zero DB calls during walk
- `calc_bom_summary` simplified to O(1) flat lookup against stored values — no recursion at read time
- `get_all_projects_with_summary` rewritten as a single SQL query — was calling `get_project_summary` per project on every dashboard load
- `get_all_parts()` dropdowns replaced with live AJAX search on BOM and project pages

---

### Phase 3 — SSOT / correctness

- `calculations.py` — `compute_quote_totals()` is the single source of truth for all pricing math; both quote GET and POST routes call it
- `discount_amount` renamed to `global_discount_component`; template updated to display `overall_discount`
- Optimistic locking in `save_quote()` via `updated_at` check
- `_upsert_part_row()` extracted — consolidates all four import functions; fixes silent loss of alt-supplier fields during XLSX and SQLite imports

---

### Phase 4 — Testing & architecture fixes

- `tests/test_calculations.py` and `tests/test_bom.py` added
- `test_bom.py` uses `tmp_path` fixture — no more `test.db` in project root
- `PRAGMA foreign_keys = ON` added to `get_db()` — was silently missing
- Partial DI reverted — `Depends(get_db)` on a single route was inconsistent and missing the FK pragma; deferred to v5.0
- `Depends` removed from FastAPI import

---

### Phase 5A — UI/UX polish

- Light mode: cooler body background, stronger card shadows, visible input resting borders
- Stat cards: hover lift + accent border glow
- Buttons: press state, `user-select:none`, border-color transitions
- `field-hint` CSS tooltip system added (pure CSS, no JS)
- `icon-btn` class for table action columns with `[data-tip]` tooltips
- Sidebar: narrowed, light mode shadow, left-border active indicator
- Tables: sticky `thead`, rounded wrap, row hover transition
- Topbar: bolder title, breadcrumb separator, `.topbar-actions` divider
- Column headers: 9px → 10px
- Print CSS unified into one block
- `dashboard.html`, `parts.html`, `project_quote.html` updated

---

### Phase 5B — JS extraction & XSS fixes

**New `static/js/` files:**
- `lems-core.js` — shared utilities (escapeHtml, showToast, apiFetch, toggleMode, toggleSidebar, inline cell edit, flag badge)
- `parts.js` — filter persistence, column sort, delete
- `part-form.js` — ID preview, unit cost recalc, alt supplier toggle
- `admin.js` — import flow, flags, print/export
- `project-quote.js` — recalcTotals, freeze/unfreeze/bump. Jinja constants moved to `data-*` on `<form>`
- `bom.js` — BOM mutations, tree fetch and render. Tree loaded via `fetch('/bom/tree/')` — page renders immediately, tree loads async
- `project-detail.js` — all order sheet mutations, custom items, packing, optional panel, live order totals. `PROJECT_ID_DETAIL` duplicate removed

**XSS fixes:** all `innerHTML` touching `part_id`, `category`, `type`, `e.message` in `admin.html` and `dashboard.html` wrapped in `escapeHtml()` / `encodeURIComponent()`

**All templates:** `{% block scripts %}` → `{% block extra_js %}`

**Live order totals:** `recalcOrderTotals()` updates on every custom item change without page reload

---

### Phase 6 — Audit trail & automatic backups

**New files:** `utils.py`, `templates/identity.html`, `templates/audit.html`, `static/js/audit.js`

**Backup strategy (configurable in `utils.py`):**
- `IDLE_BACKUP_MINUTES = 30` — idle period before a write triggers a backup
- `KEEP_BACKUPS = 10` — recent copies kept in `backups/`; older files moved to `backups/archive/`
- Startup backup always runs before any user changes
- Write backup debounced to once per idle window via `jresp()`

**Identity:** one-time name prompt on first browser visit, pre-filled with machine hostname, stored as a 1-year cookie. Sets `db._current_user` via `IdentityMiddleware` on every request.

**Audit log (`change_log` table):** field-level diff logging on all key writes:
`upsert_part`, `delete_part`, `add/update/delete_bom_row`, `upsert/delete_project`, `add/update/delete_project_item`, `set_project_item_type`, `add/update/delete_project_other_item`, `save_quote`

**`/audit` page:** filterable by entity type, entity ID, user, date range. Paginated at 100 rows. CSV export via `/api/audit/export`.

---

### Phase 7 — Exploded BOM modal

- `GET /api/bom/explode/{part_id}` endpoint added
- 🧨 button on every ASSY/FAB row of the order sheet
- Modal fetches `/bom/tree/` and renders a collapsible tree — first level auto-expands
- Each row: type badge, part ID link, description, qty, labor hours, cost
- Optional components shown in a separate section
- Backdrop click and Escape to close
- All user-sourced strings through `escapeHtml()`

---

### Post-Audit Fixes (v4.0.1)
_Applied after v4.0 audit round; all tests passing (53 total)_

#### Audit log — spurious zero-value entries
- **`_norm_for_diff()`** added to `database.py` — normalises `None`, `0`, `0.0`, `'0'` to a canonical empty string before comparison, eliminating noise entries whenever a quote was saved with all-zero default fields
- **Presence guard in `_diff_log()`** — fields absent from the incoming `data` dict are now skipped entirely; a missing key is no longer treated as a deletion, preventing false `'X → None'` entries on partial saves

#### Quote page — live recalc (SSOT enforcement)
- **`POST /projects/{project_id}/quote/preview`** endpoint added — accepts current form values, runs `calculations.compute_quote_totals()`, returns JSON; no DB writes
- **`project-quote.js` `recalcTotals()`** rewritten — replaced ~50 lines of duplicate client-side math with a 300 ms debounced `fetch()` to the preview endpoint; zero financial math now lives in JavaScript
- **`wf-line-disc-row` / `wf-line-disc`** IDs added to the waterfall discount row — enables live show/hide and value update from the preview response

#### Quote page — markup fallback bug
- **`markup_pct` None-check** in `calculations.py` — replaced `float(quote.get('markup_pct') or project.get('markup') or 0)` with an explicit `is not None` guard; a quote with `markup_pct = 0` no longer silently inherits the project's legacy `markup` value, causing inflated line-item discount bases

#### Custom line item discount bugs (`calculations.py`)
- **`discount_flat` on other items** — previously only reduced the display retail; `quoted_total` was unchanged. Fixed by tracking `total_other_disc` and deducting it from the waterfall `pre_discount`
- **`discount_pct` on other items** — previously applied to our internal cost (wrong semantics and wrong margin). Fixed: markup now applies to full `raw_cost`; discount applies to `base_retail`. Internal cost and gross margin are now accurate
- **Combined pct + flat discount** on a single other item now accumulates correctly into `total_other_disc`
- **`total_other_disc` and `total_item_disc`** added to `compute_quote_totals()` return dict
- **Waterfall display** updated to show `total_item_disc` (hardware + custom items) on the "Line Item Discounts" row instead of hardware-only `total_line_disc`

#### Hardware line-item qty double-count bug (`calculations.py`)
- `item['material_cost']` and `item['labor_cost']` are already qty-scaled by `calc_bom_summary`; the previous `ext_retail = item_retail * qty` applied qty a second time — any line item with qty > 1 had doubled discount amounts and incorrect retail. **Fixed:** `ext_retail` is now just `item_retail` (no second multiply)

#### Quote UI polish
- **Global discount inputs** — `value="{{ quote.get('discount_pct', 0) }}"` replaced with `or ''` so zero values render as empty, allowing the `%` / `$` placeholder hints to show

#### Test suite
- Test count: **50 → 53** (three new regression tests for the calculation bugs above)
- `test_other_item_discount_flat_reduces_quoted_total` — guards the `discount_flat` passthrough bug
- `test_other_item_both_discounts_reduce_quoted_total` — guards combined pct + flat on other items
- `test_hardware_line_item_qty_not_double_counted` — guards the qty double-count on hardware lines

---

### Notes for future maintenance

- `IDLE_BACKUP_MINUTES` and `KEEP_BACKUPS` are at the top of `utils.py` — update `README.md` if changed
- Full DI migration is a v5.0 candidate — not worth the churn until a DB backend change is planned
- `/bom/tree/` is shared between the BOM editor and the order sheet modal — changes to `build_bom_tree()` affect both

---

## v3.9 — Baseline
_Starting point for v4.0 development_

- `project_other_items` table introduced — migrated from `project_quotes.other_items` JSON blob
- `project_quotes.labor_rate_quoted` and `total_internal` columns added
- Clone project now carries over freight, gases, training, and labor rate settings
- Quote builder pulls other items from `project_other_items` table with per-item discount support
