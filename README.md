# LEMS ERP — v5.0.0

**Laboratory Emissions Monitoring System — Internal ERP**
Aprovecho Research Center · aprovecho.org

A locally-hosted web application for managing parts, bills of materials, project
configurations, inventory, and project quoting for the ARC LEMS monitoring kit.
The LEMS kit is a portable emissions monitoring lab ("lab in a box") deployed at
cookstove testing sites worldwide. Each kit is largely standardized but almost
always customized per project.

---

## Quick Start

### Windows
Double-click **start_lems.bat**

The script will:
1. Check that Python is installed
2. Install/update all dependencies automatically
3. Start the web server
4. Open your browser to http://localhost:8000

Keep the console window open while using the app. Close it to stop the server.

### macOS
Double-click **start_lems.command**
First time only: right-click → Open to bypass Gatekeeper.

### Manual (any platform)
```
cd lems_erp
pip install -r requirements.txt
python main.py        # Windows
python3 main.py       # macOS / Linux
```

---

## Team / Network Access

The app binds to `0.0.0.0:8000` when launched via the start scripts, meaning
anyone on the same local network can connect via:

    http://[hostname-of-host-machine]:8000

The hostname is printed in the console when the server starts.

Recommended setup for shared office use:
- Place the `lems_erp` folder on your file server (e.g. `Z:\arcfileshare\lems_erp`)
- Run `start_lems.bat` on one designated machine
- Team members open `http://[that-machine's-name]:8000` in their browser
- Only one instance of the server should run at a time

---

## Requirements

- Python 3.10 or newer (python.org)
- Dependencies (auto-installed by start scripts):
  `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `openpyxl`

---

## Application Structure

```
lems_erp/
  main.py               FastAPI routes and app entry point
  database.py           All DB logic, schema, migrations, queries
  calculations.py       Single Source of Truth for all pricing math
  utils.py              Shared utility functions
  requirements.txt
  tests/                Automated test suite (53 tests)
  start_lems.bat        Windows launcher
  start_lems.command    macOS launcher
  lems_core.db          SQLite database (live data — not in git)
  static/
    css/app.css
    img/erp_icon.ico
  templates/
    base.html
    dashboard.html
    parts.html           Part list and inline edit
    part_form.html       Create / edit a part
    bom.html             BOM editor
    print_bom.html
    projects.html        Project list
    project_detail.html  Order sheet, pick list, packing
    project_quote.html   Quote builder and pro-forma
    project_form.html
    pick_list.html
    print_project.html
    inventory.html
    where_used.html
    admin.html
```

---

## Key Features

### Parts & Master Data
- Structured part IDs: `TYPE-CATEGORY-DESC-SIZE-VARIANT`
- Primary and alternate supplier fields per part —
  toggle "use alternate supplier cost" to activate alt pricing in BOM rollups
- Part Attachments: Upload `.pdf`, `.png`, and other drawings directly to a part (stored locally)
- Cost History: Automatic chronological tracking of all part cost updates
- Last cost update date — auto-stamped when prices change
- Part statuses: `ACTIVE`, `OBSOLETE`
- Master Data Replace import — full wipe-and-reload of parts/BOM from CSV,
  with confirmation dialog (Admin page)

### BOM Management
- Unlimited-depth hierarchical BOM trees (`ASSY` > `FAB` > `PRT` / `RAW`)
- Drag-to-reorder components within an assembly
- Optional parts flagged with `[optional]` badge in all print views
- Full cost rollup: material cost + labor hours at every level
- Memo-ized rollup — shared sub-assemblies computed once regardless of how
  many times they appear in the tree
- BOM comparison tool

### Projects
- Each project = one customer kit configuration
- Clone `STD_PKG_TEMPLATE` to start new projects from the standard build
- Line item types: Standard / Option / Additional / Deleted
- Pick list with shortage tracking and commit/return inventory workflow
- Project Attachments: A single view that aggregates all file attachments for all parts in the project's BOM

### Quote Builder
Located at: **Projects → [Project] → Quote**

Internal view shows:
- Live or frozen BOM material cost
- Overhead rate multiplier (shop burden recovery)
- Labor cost (hours × rate)
- Freight: inbound purchasing + outbound to customer
- Calibration gases: CO/CO₂ cylinders + direct-ship freight
- Training: days, total cost, notes
- Custom line items (with optional Pro-Forma visibility)
- Markup % → Quoted price → Gross margin %

Pro-Forma view (customer-facing):
- Prints directly from the browser — internal costs and margins never visible
- Version number tracks quote revisions
- Costs can be frozen at a point-in-time snapshot

### Inventory & Count Sheet
- Stock levels, on-order quantity, ETA
- Count sheet mode (print-ready clean table)
- Global need calculation across all active projects

### Admin
- **Import:** CSV backup restore, SQLite `.db` file, Excel workbook (`.xlsx`)
  — all imports enforce a 50 MB size cap
- **Master Data Replace:** wipes parts + BOM, reloads clean (no ghost IDs)
- **Export:** full CSV backup
- **System Flags:** zero-cost parts, empty BOMs, obsolete parts in active use,
  and more — expandable to show full lists

---

## Data Management

### Routine Backup
**Admin → Export / Backup → Download Backup CSV**
Download before any risky import or major editing session. The app also
maintains automatic rolling backups in `_backups/` — one is taken on startup,
then again after the first write following 30 minutes of inactivity.

### Editing the Master Parts List
1. Export a backup CSV
2. Edit parts/BOM rows in a spreadsheet
3. **Admin → Master Data Replace** — uploads clean, wipes old data
4. Confirm the dialog — this cannot be undone without a backup

### Updating Part Costs
Edit any `PRT` or `RAW` part directly. The `last_cost_date` field is
auto-stamped when `pkg_cost` or `pkg_cost_2` changes. Run a rollup from the
BOM page after bulk cost updates.

---

## Part ID Convention

```
  TYPE  - CATEGORY - BASE_DESC   - SIZE_SPEC - VARIANT
   PRT  -   ELC    - RESISTOR    - 10K-1/4W  - 1PCT
   FAB  -   ENC    - PANEL-FRONT
  ASSY  -   STD    - STDPKG
```

Types: `ASSY` `FAB` `PRT` `RAW`

---

## Financial Concepts (Quick Reference)

```
  Material Cost       Purchase price of all parts, rolled up from BOM
  Overhead Rate       Multiplier (e.g. 1.15) to recover shop costs not in part prices
  Burdened Material   Material Cost × Overhead Rate
  Labor Cost          Touch-time hours × labor rate
  Total Internal Cost Everything it costs ARC to deliver the project
  Markup %            Added on top of Total Cost to arrive at the quoted price
  Quoted Price        What the customer pays
  Gross Margin %      (Quoted − Cost) / Quoted — target ≥ 15% for reserve generation
  Contribution Margin Revenue remaining after direct costs of one project
```

As a non-profit, surplus is not "profit" — it funds equipment replacement,
R&D, and organizational reserves. Pricing below true cost depletes reserves
even when it "breaks even" on paper.

---

## Running the Test Suite

```
cd lems_erp
pip install -r requirements.txt
pytest tests/ -v
```

All 53 tests should pass. Tests cover BOM math, circular reference detection,
pricing calculations, and flat BOM explosion logic.

---

## Version History

### v5.0.0
- **Part Attachments**: Local file upload and storage for part drawings/attachments, with a project-level aggregation modal.
- **Cost History**: Chronological tracking and UI modal for part cost changes.
- **Inventory Need Fix**: Global need accurately excludes items already picked in active projects to prevent inflated re-order counts.

### v4.0.3
- Fixed `_current_user` global replaced with `contextvars.ContextVar` — prevents
  audit log writing the wrong user name when concurrent async requests overlap
- Import temp files now use unique names via `tempfile.NamedTemporaryFile` —
  eliminates a race condition if two users trigger an admin import simultaneously
- All four admin import endpoints now enforce a 50 MB upload size cap via a
  shared `_read_upload()` helper; temp files cleaned up in `finally` on all paths
- Added detailed ordering explanation to `run_rollup_for_part_and_ancestors`
- Clarified `labor_cost` vs `total_labor_hrs` semantic split in `get_project_summary`

### v4.0.2
Post-audit cleanups — all 53 tests passing:
- Duplicate HTML ID `sc-mat-burdened2` fixed (BOM Costs waterfall row was stale after live recalc)
- Stale `quote.other_items` loop removed from `project_quote.html`
- `total_internal` now written on quote POST (was only written on GET)
- `markup_pct` guard consistent with `calculations.py`

### v4.0.0 — Infrastructure & Performance Modernization
- **Calculations SSOT** — all pricing, markup, and discount math extracted into
  `calculations.py`. Identical results between UI and database; no calculation drift.
- **Performance** — WAL mode enabled. Recursive BOM algorithms flattened to use
  shared connections, eliminating N+1 overhead. Memoization for large rollups.
- **Reliability** — `pytest` suite introduced in `/tests`.
- **Concurrency** — Optimistic locking (`updated_at`) on project saves prevents
  users from overwriting each other during multi-user LAN sessions.
- **Audit trail** — `change_log` table captures old and new values for all
  field-level edits, with user attribution.

### v3.9
Major restructure of quoting and project workflow. Custom/Quoted Items moved
from quote JSON blob to `project_other_items` DB table. Quoted Labor Rate moved
to the Quote page only. Quote waterfall rebuilt as a full stacked calculation
table. Full CSV export/import round-trip.

### v3.8
Projects list shows actual quoted price + GM%. Order sheet totals show
Material + Labor = Total Cost only. Per-line % and $ discounts. Packing
metadata: boxes, pallets, weights, dimensions.

### v3.7
Quote builder framework. Alt supplier fields + `last_cost_date`. Admin flags
expand-all. Project detail dropdown fix.

### v3.5 – v3.6
UI polish (Inter font, focus rings). Admin flags bug fix.

### v2.7
BOM dropdown fix, print indent, optional badge, Master Data Replace.

---

*LEMS ERP is an internal tool developed for Aprovecho Research Center.*
*Not for public distribution.*
