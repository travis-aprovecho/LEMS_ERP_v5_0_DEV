import os

with open('database.py', 'r', encoding='utf-8') as f:
    db = f.read()

db = db.replace(
    "SELECT * FROM parts WHERE deleted_at IS NULL",
    "SELECT * FROM parts WHERE 1=1"
)

db = db.replace(
    '''def delete_part(part_id: str) -> tuple[bool, str]:
    with get_conn() as conn:
        conn.execute("UPDATE parts SET deleted_at = datetime('now') WHERE part_id = ?", (part_id,))
        log_change(conn, 'part', part_id, 'delete')
    return True, "Part soft-deleted."''',
    '''def delete_part(part_id: str) -> tuple[bool, str]:
    with get_conn() as conn:
        conn.execute("UPDATE parts SET status = 'OBSOLETE' WHERE part_id = ?", (part_id,))
        log_change(conn, 'part', part_id, 'obsolete')
    return True, "Part marked as obsolete."'''
)

db = db.replace(
    "p.plain_desc, p.type, p.unit_cost, p.uom, p.status, p.deleted_at",
    "p.plain_desc, p.type, p.unit_cost, p.uom, p.status"
)

db = db.replace(
    "'status':     p.get('status', 'ACTIVE'),\n            'deleted_at': p.get('deleted_at')",
    "'status':     p.get('status', 'ACTIVE')"
)

with open('database.py', 'w', encoding='utf-8') as f:
    f.write(db)

# Now fix templates
templates = ['bom.html', 'print_bom.html', 'print_project.html', 'project_detail.html']
for t in templates:
    with open(f"templates/{t}", 'r', encoding='utf-8') as f:
        html = f.read()
    
    html = html.replace(" or c.deleted_at", "")
    html = html.replace(" or row.deleted_at", "")
    html = html.replace(" or item.deleted_at", "")
    
    html = html.replace("{% if c.deleted_at %}DEL{% else %}OBS{% endif %}", "OBS")
    html = html.replace("{% if row.deleted_at %}DEL{% else %}OBS{% endif %}", "OBS")
    html = html.replace("{% if item.deleted_at %}DEL{% else %}OBS{% endif %}", "OBS")
    
    with open(f"templates/{t}", 'w', encoding='utf-8') as f:
        f.write(html)

print("DB and templates patched")
