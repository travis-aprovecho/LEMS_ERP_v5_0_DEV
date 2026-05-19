# LEMS ERP v5.0 Implementation Plan

This plan formalizes the agreed-upon engineering roadmap for v5.0. It prioritizes data integrity, performance, and operational capability without succumbing to over-engineering.

## User Review Required

> [!IMPORTANT]
> Please review this finalized scope. If approved, we will begin executing these phases sequentially. Phase 1 (Foundation) must be completed before the other phases to ensure database stability.

## Proposed Changes

### Phase 1: Foundation & Safe Renaming
Establishes a safe architectural baseline for all subsequent work.

- **FastAPI Dependency Injection (`main.py`):**
  - Migrate all route handlers to use `Depends(get_db)`.
  - Remove global `DB_PATH` dependencies from route logic to allow safe, in-memory end-to-end testing.
- **Formal Database Migration System (`database.py`):**
  - Replace the current `try/except: pass` `_migrate_schema` loop with a formal `schema_migrations` table.
  - Number each schema change sequentially so the database state is perfectly reproducible and auditable.
- **`ON UPDATE CASCADE` for Part Renaming (`database.py`):**
  - Write a migration to add `ON UPDATE CASCADE` to the foreign keys in `project_items` and `project_pick_status`.
  - Build a `/admin/rename_part` API utility to allow safe, instant part renaming across the entire system.

---

### Phase 2: Type Safety & Testing
Locks in the current behavior and prevents silent regressions.

- **Enum Types for Constants (`database.py`):**
  - Convert `TYPES`, `CATEGORIES`, `PART_STATUSES`, and `ITEM_TYPES` from plain lists of strings into strict Python `Enum` classes to prevent typos from silently corrupting the database.
- **Write-Path Test Coverage (`tests/`):**
  - Add end-to-end tests covering `import_master_data`, `import_from_xlsx`, quote saves, and project cloning to ensure these complex operations never silently drop data.

---

### Phase 3: Performance & Hygiene
Fixes the remaining bottlenecks without adding complex background infrastructure.

- **O(1) Memory BOM Traversal (`database.py`):**
  - Rewrite `explode_bom_flat` and related adjacency functions.
  - Instead of recursively hitting SQLite (N+1 queries), load `SELECT * FROM bom` into a Python dictionary at the start of the function and perform the topological sort and rollup in memory. This executes in milliseconds.
- **Change Log Archival (`utils.py` & `main.py`):**
  - Add a configurable retention window (e.g., 12 months) for the `change_log` table.
  - Create an automated startup job that moves older entries out of SQLite and into a compressed `.csv` archive file to keep the active database lean.

---

### Phase 4: Data Integrity (New Additions)
Ensures historical project data is never mutated by future edits.

- **Immutable Quote Snapshots (`database.py`):**
  - Create a `quote_snapshots` table.
  - When a quote is marked as "Sent" or "Accepted", serialize its exact BOM, line-item pricing, and custom items into an immutable JSON blob. This guarantees historical quotes will never change even if a user edits a custom item's cost months later.
- **Soft Deletes (`database.py`):**
  - Add a `deleted_at` timestamp to the `parts` table.
  - Replace physical `DELETE` operations with soft-deletes so historical BOMs and quotes can still resolve their original references without throwing foreign-key errors.

---

### Phase 5: New Features & Operations
The high-value operational tools for daily use.

- **Purchase Order / Reorder List (`main.py` & `templates/`):**
  - Add a new dashboard page that aggregates shortage data (`qty_on_hand` < needed) across all active projects.
  - Group shortages by preferred supplier into draft purchase orders ready for export.
- **Part Cost History (`database.py` & `templates/`):**
  - Create a `part_cost_history` table that logs a timestamped entry every time a part's `unit_cost` changes.
  - Display the price timeline on the part detail page to track margin drift and supplier price hikes.
- **Docker Image (`Dockerfile` & `docker-compose.yml`):**
  - Package the app, its dependencies, and the launcher into a single deployable image.
  - Mount the `lems_core.db` and `backups/` directories as persistent volumes.

## Verification Plan

### Automated Tests
- Run `pytest` to ensure all 53 existing tests pass.
- Verify the new Phase 2 tests successfully catch deliberate data-loss injections in the import functions.

### Manual Verification
- Test the new `/admin/rename_part` API by renaming a deeply nested component and verifying the ID propagates to all quotes and BOMs.
- Confirm BOM explosion speeds on the largest assembly are visibly instantaneous compared to v4.
- Create a test quote, freeze it, modify the underlying custom item costs, and verify the quote remains mathematically unchanged using the new Immutable Snapshot feature.
