# LEMS Development Rules

## 🔒 Database & Calculations
- **Migrations:** Any code modification that alters the database schema must contain a corresponding migration entry in `_migrate_schema()`. Never run manual migration SQL commands outside this function.
- **Rollups:** Call `run_rollup_for_part_and_ancestors(part_id)` immediately after any database modification to a BOM structure or a part's cost.
- **Upserts:** Always delegate external imports (CSV, XLSX, SQLite merges) to `_upsert_part_row(conn, row)`. Never use raw `INSERT OR REPLACE INTO parts` statements.
- **Single Source of Truth:** All quote calculations and price recalculations must route through `calculations.py`. Do not duplicate math in JS or FastAPI route files.

## 🎨 Styling & Frontend
- **CSS Variables:** Under no circumstances should hex colors (e.g., `#ffffff`) be committed to CSS files. Always use the specified CSS variables in `app.css`.
- **No Inline Styles/Scripts:** All CSS rules go in `app.css`. All page-specific JS goes in `static/js/{page}.js` loaded via `{% block extra_js %}`. Do not inline styles/scripts in HTML templates.
- **HTML Escaping:** Any database or user-supplied string assigned via `innerHTML` in JavaScript must be wrapped in `escapeHtml()`.

## ⚙️ Coding Standards
- **Naming Conventions:** Use `snake_case` for Python functions and variables, and `camelCase` for JavaScript variables and functions.
- **JSON Mutation Responses:** All API write/POST routes in `main.py` must return responses using the unified `jresp(ok, msg, **extra)` helper.
