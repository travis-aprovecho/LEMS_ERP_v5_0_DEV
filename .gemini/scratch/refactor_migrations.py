import re

def main():
    with open('database.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find where _migrate_schema and _migrate_other_items are called
    content = content.replace(
        "        _migrate_schema(conn)\n        _migrate_other_items(conn)",
        "        _run_migrations(conn)"
    )

    # We want to replace everything from `def _migrate_schema(conn):` down to the end of `_migrate_other_items(conn)`
    # Let's find their bounds.
    start_migrate = content.find("def _migrate_schema(conn):")
    
    # We need to find the end of `_migrate_other_items`.
    # It ends with `except Exception:\n        pass\n`
    end_migrate = content.find("    except Exception:\n        pass\n", start_migrate)
    if end_migrate != -1:
        end_migrate += len("    except Exception:\n        pass\n")

    migrations_code = """def _run_migrations(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    current_version = row[0] if row[0] else 0

    migrations = [
        (1, _migration_v1_legacy),
        (2, _migration_v2_other_items),
        (3, _migration_v3_on_update_cascade),
    ]

    for version, func in migrations:
        if version > current_version:
            try:
                func(conn)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"Migration v{version} failed: {e}")
                raise

def _migration_v1_legacy(conn):
    def col_exists(table, col):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return col in cols

    stmts = [
        ("parts", "status",       "ALTER TABLE parts ADD COLUMN status TEXT DEFAULT 'ACTIVE'"),
        ("parts", "rolled_labor_hrs", "ALTER TABLE parts ADD COLUMN rolled_labor_hrs REAL DEFAULT 0"),
        ("bom",   "sort_order",   "ALTER TABLE bom ADD COLUMN sort_order INTEGER DEFAULT 0"),
        ("projects", "markup",    "ALTER TABLE projects ADD COLUMN markup REAL DEFAULT 0"),
        ("projects", "created_at","ALTER TABLE projects ADD COLUMN created_at TEXT DEFAULT (datetime('now'))"),
        ("parts", "supplier_2",   "ALTER TABLE parts ADD COLUMN supplier_2 TEXT DEFAULT ''"),
        ("parts", "brand_mfg_2",  "ALTER TABLE parts ADD COLUMN brand_mfg_2 TEXT DEFAULT ''"),
        ("parts", "supplier_pn_2","ALTER TABLE parts ADD COLUMN supplier_pn_2 TEXT DEFAULT ''"),
        ("parts", "pkg_size_2",   "ALTER TABLE parts ADD COLUMN pkg_size_2 REAL DEFAULT 1"),
        ("parts", "pkg_cost_2",   "ALTER TABLE parts ADD COLUMN pkg_cost_2 REAL DEFAULT 0"),
        ("parts", "unit_cost_2",  "ALTER TABLE parts ADD COLUMN unit_cost_2 REAL DEFAULT 0"),
        ("parts", "use_alt_supplier", "ALTER TABLE parts ADD COLUMN use_alt_supplier INTEGER DEFAULT 0"),
        ("parts", "last_cost_date",   "ALTER TABLE parts ADD COLUMN last_cost_date TEXT DEFAULT ''"),
        ("project_quotes", "markup_pct", "ALTER TABLE project_quotes ADD COLUMN markup_pct REAL DEFAULT 0"),
        ("project_items", "item_type", "ALTER TABLE project_items ADD COLUMN item_type TEXT DEFAULT 'ADDITIONAL'"),
        ("project_items", "box_num", "ALTER TABLE project_items ADD COLUMN box_num TEXT DEFAULT ''"),
        ("project_quotes", "discount_pct",  "ALTER TABLE project_quotes ADD COLUMN discount_pct  REAL DEFAULT 0"),
        ("project_quotes", "discount_flat", "ALTER TABLE project_quotes ADD COLUMN discount_flat REAL DEFAULT 0"),
        ("project_quotes", "discount_note", "ALTER TABLE project_quotes ADD COLUMN discount_note TEXT DEFAULT ''"),
        ("project_quotes", "labor_rate_quoted", "ALTER TABLE project_quotes ADD COLUMN labor_rate_quoted REAL DEFAULT 0"),
        ("project_quotes", "total_internal",   "ALTER TABLE project_quotes ADD COLUMN total_internal REAL DEFAULT 0"),
        ("project_quotes", "quoted_total",     "ALTER TABLE project_quotes ADD COLUMN quoted_total REAL DEFAULT 0"),
        ("project_quotes", "gross_margin_pct", "ALTER TABLE project_quotes ADD COLUMN gross_margin_pct REAL DEFAULT 0"),
        ("project_items", "discount_pct",  "ALTER TABLE project_items ADD COLUMN discount_pct REAL DEFAULT 0"),
        ("project_items", "discount_flat", "ALTER TABLE project_items ADD COLUMN discount_flat REAL DEFAULT 0"),
        ("parts",               "qty_on_order", "ALTER TABLE parts ADD COLUMN qty_on_order REAL DEFAULT 0"),
        ("parts",               "order_eta",    "ALTER TABLE parts ADD COLUMN order_eta TEXT DEFAULT ''"),
        ("project_pick_status", "picked_qty",   "ALTER TABLE project_pick_status ADD COLUMN picked_qty REAL DEFAULT 0"),
        ("change_log", "id", \"\"\"CREATE TABLE IF NOT EXISTS change_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            user        TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            action      TEXT NOT NULL,
            field       TEXT,
            old_val     TEXT,
            new_val     TEXT
        )\"\"\"),
    ]
    for table, col, sql in stmts:
        try:
            if sql.strip().upper().startswith('CREATE TABLE'):
                exists = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
                if not exists: conn.executescript(sql)
            elif not col_exists(table, col):
                conn.execute(sql)
        except Exception:
            pass

    conn.execute("UPDATE bom SET sort_order = rowid WHERE sort_order = 0 AND parent_id != '' AND parent_id IS NOT NULL")
    try:
        conn.execute("UPDATE project_items SET item_type = 'STANDARD' WHERE item_type IS NULL OR item_type = 'ADDITIONAL' AND part_id LIKE '%-STDPKG%'")
    except Exception:
        pass

def _migration_v2_other_items(conn):
    import json
    try:
        quotes = conn.execute("SELECT project_id, other_items FROM project_quotes WHERE other_items IS NOT NULL AND other_items != '[]'").fetchall()
        for q in quotes:
            existing = conn.execute("SELECT COUNT(*) FROM project_other_items WHERE project_id=?", (q['project_id'],)).fetchone()[0]
            if existing > 0: continue
            items = json.loads(q['other_items'] or '[]')
            for idx, i in enumerate(items):
                if not isinstance(i, dict): continue
                conn.execute(
                    \"\"\"INSERT INTO project_other_items
                       (project_id, description, cost, labor_hrs, apply_markup, box_num, discount_pct, discount_flat, show_on_proforma, sort_order)
                       VALUES (?,?,?,?,?,?,?,?,?,?)\"\"\",
                    (q['project_id'], (i.get('desc') or i.get('description') or '').strip(), float(i.get('cost') or 0), float(i.get('labor_hrs') or 0), 1 if i.get('apply_markup') else 0, (i.get('box_num') or '').strip(), float(i.get('discount_pct') or 0), float(i.get('discount_flat') or 0), 1 if i.get('show_on_proforma') else 0, idx)
                )
    except Exception:
        pass

def _migration_v3_on_update_cascade(conn):
    conn.executescript(\"\"\"
        CREATE TABLE IF NOT EXISTS new_project_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            part_id    TEXT NOT NULL REFERENCES parts(part_id) ON UPDATE CASCADE,
            qty        REAL DEFAULT 1,
            picked     INTEGER DEFAULT 0,
            item_type  TEXT DEFAULT 'ADDITIONAL',
            box_num    TEXT DEFAULT '',
            discount_pct  REAL DEFAULT 0,
            discount_flat REAL DEFAULT 0
        );
        INSERT INTO new_project_items (id, project_id, part_id, qty, picked, item_type, box_num, discount_pct, discount_flat)
        SELECT id, project_id, part_id, qty, picked, item_type, box_num, discount_pct, discount_flat FROM project_items;
        DROP TABLE project_items;
        ALTER TABLE new_project_items RENAME TO project_items;
        CREATE INDEX IF NOT EXISTS idx_project_items_pid ON project_items(project_id);

        CREATE TABLE IF NOT EXISTS new_project_pick_status (
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            part_id    TEXT NOT NULL REFERENCES parts(part_id) ON UPDATE CASCADE,
            picked     INTEGER DEFAULT 0,
            picked_qty REAL DEFAULT 0,
            PRIMARY KEY (project_id, part_id)
        );
        INSERT INTO new_project_pick_status (project_id, part_id, picked, picked_qty)
        SELECT project_id, part_id, picked, picked_qty FROM project_pick_status;
        DROP TABLE project_pick_status;
        ALTER TABLE new_project_pick_status RENAME TO project_pick_status;
        CREATE INDEX IF NOT EXISTS idx_project_pick_pid ON project_pick_status(project_id);
    \"\"\")
"""

    # We also need to remove _migrate_other_items from where it is defined
    # Actually wait! The `end_migrate` above only deleted up to `_migrate_schema`. 
    # _migrate_other_items is way down at line 1409!
    # It's safer to delete them individually.
    
    # 1. Replace _migrate_schema
    start_migrate = content.find("def _migrate_schema(conn):")
    end_migrate = content.find("    except Exception:\n        pass\n", start_migrate) + len("    except Exception:\n        pass\n")
    content = content[:start_migrate] + migrations_code + content[end_migrate:]

    # 2. Delete _migrate_other_items
    start_other = content.find("def _migrate_other_items(conn):")
    if start_other != -1:
        end_other = content.find("    except Exception:\n        pass\n", start_other) + len("    except Exception:\n        pass\n")
        content = content[:start_other] + content[end_other:]

    with open('database.py', 'w', encoding='utf-8') as f:
        f.write(content)

main()
