import sys

def patch_db():
    with open("database.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 1. Add v6 to _run_migrations
        if line.strip() == "(5, _migration_v5_cost_history),":
            out.append(line)
            out.append("        (6, _migration_v6_attachments),\n")
            i += 1
            continue
            
        # 2. Add _migration_v6_attachments definition after v5
        if line.startswith("def _migration_v5_cost_history(conn):"):
            out.append(line)
            i += 1
            while i < len(lines) and lines[i].startswith("    "):
                out.append(lines[i])
                i += 1
            out.append("\n")
            out.append("def _migration_v6_attachments(conn):\n")
            out.append("    conn.execute('''\n")
            out.append("        CREATE TABLE IF NOT EXISTS part_attachments (\n")
            out.append("            id TEXT PRIMARY KEY,\n")
            out.append("            part_id TEXT,\n")
            out.append("            filename TEXT,\n")
            out.append("            original_filename TEXT,\n")
            out.append("            mime_type TEXT,\n")
            out.append("            size_bytes INTEGER,\n")
            out.append("            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n")
            out.append("            uploaded_by TEXT,\n")
            out.append("            FOREIGN KEY(part_id) REFERENCES parts(part_id) ON UPDATE CASCADE ON DELETE CASCADE\n")
            out.append("        )\n")
            out.append("    ''')\n")
            continue
            
        out.append(line)
        i += 1
        
    # 3. Add Attachment functions at the end of the file
    out.append("\n")
    out.append("# ── Attachments ────────────────────────────────────────────────────────────────\n")
    out.append("def get_part_attachments(part_id: str) -> list[dict]:\n")
    out.append("    with get_conn() as conn:\n")
    out.append("        return [dict(r) for r in conn.execute(\n")
    out.append("            \"SELECT * FROM part_attachments WHERE part_id=? ORDER BY uploaded_at DESC\",\n")
    out.append("            (part_id,)\n")
    out.append("        ).fetchall()]\n\n")
    
    out.append("def get_project_attachments(project_id: str) -> list[dict]:\n")
    out.append("    # First, get all parts in the project BOM using explode_bom_flat\n")
    out.append("    with get_conn() as conn:\n")
    out.append("        bom_ctx = _build_bom_ctx(conn)\n")
    out.append("        items = conn.execute(\"SELECT part_id, qty FROM project_items WHERE project_id=? AND item_type != 'DELETED'\", (project_id,)).fetchall()\n")
    out.append("        \n")
    out.append("        part_ids = set()\n")
    out.append("        for item in items:\n")
    out.append("            flat = explode_bom_flat(item['part_id'], qty_mult=1.0, _conn=conn, bom_ctx=bom_ctx)\n")
    out.append("            for r in flat:\n")
    out.append("                part_ids.add(r['part_id'])\n")
    out.append("        \n")
    out.append("        if not part_ids: return []\n")
    out.append("        \n")
    out.append("        placeholders = ','.join('?' for _ in part_ids)\n")
    out.append("        rows = conn.execute(\n")
    out.append("            f\"SELECT * FROM part_attachments WHERE part_id IN ({placeholders}) ORDER BY uploaded_at DESC\",\n")
    out.append("            tuple(part_ids)\n")
    out.append("        ).fetchall()\n")
    out.append("        return [dict(r) for r in rows]\n\n")

    out.append("def add_part_attachment(data: dict) -> bool:\n")
    out.append("    with get_conn() as conn:\n")
    out.append("        conn.execute('''\n")
    out.append("            INSERT INTO part_attachments (id, part_id, filename, original_filename, mime_type, size_bytes, uploaded_by)\n")
    out.append("            VALUES (:id, :part_id, :filename, :original_filename, :mime_type, :size_bytes, :uploaded_by)\n")
    out.append("        ''', data)\n")
    out.append("        return True\n\n")

    out.append("def delete_part_attachment(att_id: str) -> dict | None:\n")
    out.append("    with get_conn() as conn:\n")
    out.append("        row = conn.execute(\"SELECT * FROM part_attachments WHERE id=?\", (att_id,)).fetchone()\n")
    out.append("        if not row: return None\n")
    out.append("        conn.execute(\"DELETE FROM part_attachments WHERE id=?\", (att_id,))\n")
    out.append("        return dict(row)\n")

    with open("database.py", "w", encoding="utf-8") as f:
        f.writelines(out)

if __name__ == "__main__":
    patch_db()
