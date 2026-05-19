import re

with open('database.py', 'r', encoding='utf-8') as f:
    content = f.read()

upsert_func = """def _upsert_part_row(conn, row_dict: dict):
    \"\"\"Unified upsert logic for parts table imports.\"\"\"
    part_id = str(row_dict.get('part_id') or '').strip()
    if not part_id: return
    pkg_size  = float(row_dict.get('pkg_size')  or 1)
    pkg_cost  = float(row_dict.get('pkg_cost')  or 0)
    unit_cost = float(row_dict.get('unit_cost') or 0)
    ptype     = str(row_dict.get('type') or '').strip()
    if ptype in PART_TYPES_STATIC_COST and pkg_size > 0 and pkg_cost > 0:
        unit_cost = round(pkg_cost / pkg_size, 6)
    pkg_size_2  = float(row_dict.get('pkg_size_2')  or 1)
    pkg_cost_2  = float(row_dict.get('pkg_cost_2')  or 0)
    unit_cost_2 = float(row_dict.get('unit_cost_2') or 0)
    if ptype in PART_TYPES_STATIC_COST and pkg_size_2 > 0 and pkg_cost_2 > 0:
        unit_cost_2 = round(pkg_cost_2 / pkg_size_2, 6)
    use_alt = int(bool(row_dict.get('use_alt_supplier') and str(row_dict.get('use_alt_supplier')) not in ('0','')))
    
    conn.execute(\"\"\"INSERT OR REPLACE INTO parts
        (part_id,type,category,base_desc,size_spec,variant,plain_desc,
         supplier,brand_mfg,supplier_pn,uom,pkg_size,pkg_cost,unit_cost,
         labor_hrs,qty_on_hand,cost,on_hand,status,
         supplier_2,brand_mfg_2,supplier_pn_2,pkg_size_2,pkg_cost_2,
         unit_cost_2,use_alt_supplier,last_cost_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    \"\"\", (
        part_id, ptype,
        str(row_dict.get('category')    or '').strip(),
        str(row_dict.get('base_desc')   or '').strip(),
        str(row_dict.get('size_spec')   or '').strip(),
        str(row_dict.get('variant')     or '').strip(),
        str(row_dict.get('plain_desc')  or '').strip(),
        str(row_dict.get('supplier')    or '').strip(),
        str(row_dict.get('brand_mfg')   or '').strip(),
        str(row_dict.get('supplier_pn') or '').strip(),
        str(row_dict.get('uom')         or 'ea').strip(),
        pkg_size, pkg_cost, unit_cost,
        float(row_dict.get('labor_hrs')   or 0),
        float(row_dict.get('qty_on_hand') or 0),
        float(row_dict.get('cost')        or 0),
        float(row_dict.get('on_hand')     or 0),
        str(row_dict.get('status') or 'ACTIVE').strip(),
        str(row_dict.get('supplier_2')    or '').strip(),
        str(row_dict.get('brand_mfg_2')   or '').strip(),
        str(row_dict.get('supplier_pn_2') or '').strip(),
        pkg_size_2, pkg_cost_2, unit_cost_2, use_alt,
        str(row_dict.get('last_cost_date') or '').strip(),
    ))

# ── CSV Import ─────────────────────────────────────────────────────────────────
"""

# Replace the CSV Import header to insert the function
content = content.replace("# ── CSV Import ─────────────────────────────────────────────────────────────────\n", upsert_func)

# 1. import_from_csv_data
patt1 = r"part_id = \(row\.get\('part_id'\).*?results\['parts'\] \+= 1"
content = re.sub(patt1, "_upsert_part_row(conn, row)\n                    results['parts'] += 1", content, count=1, flags=re.DOTALL)

# 2. import_master_data
patt2 = r"part_id = \(row\.get\('part_id'\).*?results\['parts'\] \+= 1"
content = re.sub(patt2, "_upsert_part_row(conn, row)\n                    results['parts'] += 1", content, count=1, flags=re.DOTALL)

# 3. import_from_sqlite
patt3 = r"pkg_size  = float\(r\.get\('pkg_size'\).*?results\['parts'\] \+= 1"
content = re.sub(patt3, "_upsert_part_row(dst, r)\n                results['parts'] += 1", content, count=1, flags=re.DOTALL)

# 4. import_from_xlsx
patt4 = r"part_id = str\(r\.get\('part_id'\).*?results\['parts'\] \+= 1"
content = re.sub(patt4, "_upsert_part_row(dst, r)\n                    results['parts'] += 1", content, count=1, flags=re.DOTALL)

with open('database.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
