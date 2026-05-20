# LEMS ERP Project History — Modernization (v4.0) & Upgrade (v5.0)

This document provides a chronological timeline and summary of the engineering work done across previous conversations on the **LEMS ERP** codebase, reconstructing the history of both the **v4.0 Modernization** and **v5.0 Upgrade** projects.

---

## 📅 Timeline Overview

```mermaid
gantt
    title LEMS ERP Project Evolution
    dateFormat  YYYY-MM-DD
    section LEMS ERP v4.0
    Phase 2 Performance & Concurrency   :active, 2026-05-10, 4d
    Phase 3 SSOT & calculations.py       :active, 2026-05-14, 2d
    v4.0 Quality & Security Audit       :active, 2026-05-16, 1d
    Audit Fixes & UI Sweep              :active, 2026-05-17, 2d
    section LEMS ERP v5.0
    Phase 1 & 2: DI, Migrations, Enums  :active, 2026-05-18, 1d
    Phase 3 & 4: Memory BOM, Archiving  :active, 2026-05-19, 1d
```

---

## 🛠️ LEMS ERP v4.0 Modernization Project

The v4.0 sprint focused on converting a sluggish, concurrency-blocked monolithic app into a fast, thread-safe, and audited production system.

### Phase 2: Performance & Concurrency
* **SQLite Optimization:** Switched SQLite connection to WAL (Write-Ahead Logging) mode and `synchronous=NORMAL` inside `init_db()`. This enabled concurrent reads/writes without the database locking on multi-user LAN setups.
* **Database Indexing:** Created critical indexes on keys in `bom(child_id)`, `bom(parent_id)`, `project_items`, and `project_pick_status` to optimize nested joins.
* **Recursive Connection Flattening:** Replaced N+1 connection spawns inside `build_bom_tree`, `explode_bom_flat`, and `_collect_where_used` by passing a single request-level connection (`_conn`) down the recursion tree.
* **O(N) Memoized Rollups:** Added the `rolled_labor_hrs` database column. Implemented memoization in `rollup_all` to roll up both material and labor costs in a single topological pass, turning rollup into an $O(N)$ operation instead of $O(N^2)$.
* **O(1) Summaries:** Rewrote `calc_bom_summary` to load pre-calculated totals instantly from the `parts` table, eliminating recursive BOM walks at read time.
* **Single-Pass Project Dashboard:** Rewrote the `/projects` handler (`get_all_projects_with_summary`) to aggregate data for all projects via 4 structured batch queries, grouping the results in Python memory. This eliminated N+1 dashboard database queries.
* **Bandwidth Optimization:** Removed heavy redundant parts-list payloads from `/projects` and BOM template routes since the frontend had migrated to AJAX live searches.

### Phase 3: SSOT, Correctness & Safety
* **Central Math Engine:** Extracted all pricing calculations from route files into a single, definitive module: [calculations.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/calculations.py).
* **Optimistic Locking:** Embedded `updated_at` hidden fields in quote edit forms and verified them inside `save_quote()` to prevent users from overwriting concurrent edits.
* **Safe Imports:** Refactored SQL upsert queries into a centralized `_upsert_part_row` function, resolving a silent data-loss bug that dropped secondary suppliers and costs during Excel/DB imports.

### Phase 4: Testing & Clean Architecture
* **FastAPI Dependency Injection:** Standardized request lifecycle connection management using `get_db()` context-variable-aware injection.
* **Test Suite:** Built automated test files `test_calculations.py` and `test_bom.py` to cover calculation formulas, circular BOM reference safeguards, flattening, and rollups.

### Post-Audit & UI Polishing
* **Critical Bug Fixes:** Resolved a severe route-naming collision in `main.py` where a second duplicate definition of `bom_index` overwrote the BOM editor handler.
* **Audit Resolutions:** Refactored `_would_create_cycle` and `get_project_optional_items` to eliminate nested connections. Fixed missing audit logs inside `update_part_field`.
* **Pick List Persist & Deduct:** Implemented persistent check-state for pick lists, a **Commit Picks** AJAX post, and a deduction script to decrement `parts.qty_on_hand` upon picking.
* **Discount System:** Introduced database schema entries and calculation paths for global flat/percent quote-level discounts.

---

## 🚀 LEMS ERP v5.0 Upgrade Project

The v5.0 roadmap prioritizes complete database decoupling, migration auditing, strict type safety, O(1) in-memory traversals, and immutable snapshots.

### Phase 1: Foundation & Safe Renaming
* **FastAPI Request-Scoped Connections:** Fully migrated routes to route-scoped async `Depends(get_db)` using `contextvars`, decoupling the engine from global scope and enabling in-memory unit tests.
* **Database Migrations:** Replaced the legacy `try/except: pass` initialization loop in [database.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/database.py) with a transaction-backed `schema_migrations` tracking table.
* **Cascading Key Renames:** Configured native SQLite `ON UPDATE CASCADE` constraints on the foreign keys of dependent tables. The `/admin/rename_part` utility can now instantly rename parts across all quotes and BOMs with a single UPDATE query.

### Phase 2: Type Safety & Testing
* **Constant Enums:** Converted string lists (`TYPES`, `CATEGORIES`, `PART_STATUSES`, `ITEM_TYPES`) into strict python `StrEnum` classes (`PartType`, `PartCategory`, `PartStatus`, `ItemType`) in [database.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/database.py).
* **Write-Path Test Suite:** Added `test_imports.py` to verify write-path operations (`import_master_data`, `import_from_xlsx`, cloning, and saves).

### Phase 3: Performance & Hygiene
* **O(1) Memory BOM Traversal:** Created `_build_bom_ctx(conn)` in [database.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/database.py) to load all BOM data into Python memory on demand. Passing this context dictionary through recursive functions (`explode_bom_flat`, `run_rollup`, `build_bom_tree`, `get_where_used`) completely eliminated SQLite database operations during tree walking.
* **Change Log Archival:** Created `archive_old_change_logs(db_path, months_to_keep=12)` in [utils.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/utils.py). This utility runs on startup in [main.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/main.py) and auto-compresses log entries older than 12 months into CSV archives inside `backups/archive/` to keep the database size small.

### Phase 4: Data Integrity
* **Immutable Quote Snapshots:** Created a `quote_snapshots` table. When a quote transitions to `SENT` or `ACCEPTED`, a JSON snapshot of the full recursive BOM structure and pricing is permanently saved, shielding older quotes from future parts-cost changes.
* **Soft Deletes:** Added a `deleted_at` timestamp to the `parts` table. Replaced hard DELETE queries with soft deletes, allowing historical BOMs to resolve relations while removing deleted items from active search indices.
* **Ghost Badge Badges:** Updated templates (`bom.html`, `print_bom.html`, `print_project.html`, `project_detail.html`) to display obsolete and deleted parts with clear warning badges.

### Phase 5: New Features & Operations (Pending Completion)
* **Shortage & Purchase Orders:** Build shortage tracking dashboard to group low-stock items by supplier.
* **Cost History Log:** Store timestamped price logs in `part_cost_history` when cost updates occur.
* **Docker Packaging:** Create `Dockerfile` and `docker-compose.yml` for persistent container deployment.

---

## 🔍 Context and Location Registry

All active workspace assets can be found in [LEMS_ERP_v5_0_DEV](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV):
- **Core server logic:** [main.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/main.py)
- **Database queries/schema:** [database.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/database.py)
- **Mathematical engine:** [calculations.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/calculations.py)
- **Audit cleanup utils:** [utils.py](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/utils.py)
- **Completed upgrade plan:** [implementation_plan.md](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/dev_notes/implementation_plan.md)
- **Completed features walkthrough:** [walkthrough.md](file:///c:/Users/travb/OneDrive/Desktop/LEMS_ERP_v5_0_DEV/dev_notes/walkthrough.md)
