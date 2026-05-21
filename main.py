import io
import csv
import json
import re
import datetime
import logging
import webbrowser
import threading
import shutil
import tempfile
import os
from typing import Optional

import sqlite3
from fastapi import FastAPI, Request, Form, UploadFile, File, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

import database as db
import calculations
import utils
from starlette.middleware.base import BaseHTTPMiddleware

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(title="LEMS ERP")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


async def get_db():
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    token = db._current_conn.set(conn)
    try:
        yield conn
    finally:
        db._current_conn.reset(token)
        conn.close()

db.init_db()

# Backup on startup — before any user changes
utils.backup_db(db.DB_PATH, reason='startup')

# Archive old change logs to keep the DB lean
utils.archive_old_change_logs(db.DB_PATH, months_to_keep=12)

# ── Identity middleware ────────────────────────────────────────────────────────
IDENTITY_COOKIE = 'lems_user'
SKIP_IDENTITY   = {'/identity', '/static', '/favicon.ico', '/api/'}

class IdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        skip = any(path.startswith(p) for p in SKIP_IDENTITY)
        user = request.cookies.get(IDENTITY_COOKIE, '').strip()

        if not user and not skip:
            from fastapi.responses import RedirectResponse as RR
            return RR(f"/identity?next={request.url.path}", status_code=302)

        db.set_current_user(user or 'system')
        response = await call_next(request)
        return response

app.add_middleware(IdentityMiddleware)

UPLOAD_TMP      = os.path.join(os.path.dirname(__file__), "_tmp_upload")
ATTACHMENTS_DIR = os.path.join(os.path.dirname(__file__), "attachments")
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
ATTACHMENTS_DIR = os.path.join(os.path.dirname(__file__), "attachments")
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
IMPORT_MAX_BYTES = 50 * 1024 * 1024   # 50 MB — more than enough for any real parts DB

async def _read_upload(file: UploadFile) -> tuple[bool, bytes | str]:
    """Read an uploaded file and enforce the size cap before loading into memory.
    Returns (ok, content_bytes) on success or (False, error_message) if over the limit."""
    content = await file.read(IMPORT_MAX_BYTES + 1)
    if len(content) > IMPORT_MAX_BYTES:
        return False, f"File too large (max {IMPORT_MAX_BYTES // (1024*1024)} MB)."
    return True, content

# ── Identity prompt ────────────────────────────────────────────────────────────
@app.get("/identity", response_class=HTMLResponse)
async def identity_page(request: Request, next: str = "/", db_conn: sqlite3.Connection = Depends(get_db)):
    import socket
    hostname = socket.gethostname()
    return templates.TemplateResponse("identity.html", {
        "request": request, "next": next, "hostname": hostname
    })

@app.post("/identity")
async def identity_save(request: Request,
                        name: str = Form(...), next: str = Form("/")):
    name = name.strip()[:64]
    if not name:
        import socket
        hostname = socket.gethostname()
        return templates.TemplateResponse("identity.html", {
            "request": request, "next": next, "hostname": hostname,
            "err": "Please enter your name."
        })
    from fastapi.responses import RedirectResponse as RR
    resp = RR(next or "/", status_code=302)
    resp.set_cookie(
        key=IDENTITY_COOKIE, value=name,
        max_age=365*24*60*60,   # 1 year
        httponly=True, samesite="lax"
    )
    return resp

def jresp(ok: bool, msg: str, **extra):
    if ok:
        utils.backup_on_write_if_due(db.DB_PATH)
    return JSONResponse({"ok": ok, "msg": msg, **extra})

@app.get('/favicon.ico', include_in_schema=False)
async def favicon(db_conn: sqlite3.Connection = Depends(get_db)):
    return FileResponse("static/img/erp_icon.ico")

# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db_conn: sqlite3.Connection = Depends(get_db)):
    with db.get_conn() as conn:
        stats = {
            "parts":      conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0],
            "bom_rows":   conn.execute("SELECT COUNT(*) FROM bom").fetchone()[0],
            "projects":   conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status='ACTIVE'"
            ).fetchone()[0],
            "assemblies": conn.execute(
                "SELECT COUNT(*) FROM parts WHERE type IN ('ASSY','FAB')"
            ).fetchone()[0],
        }
        recent_projects = [dict(r) for r in conn.execute("""
            SELECT * FROM projects
            ORDER BY CASE status
                WHEN 'ACTIVE'   THEN 1
                WHEN 'COMPLETE' THEN 2
                ELSE 3 END,
            created_at DESC
            LIMIT 6
        """).fetchall()]
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "stats": stats,
        "recent_projects": recent_projects,
    })

# ── Parts ──────────────────────────────────────────────────────────────────────

@app.get("/parts", response_class=HTMLResponse)
async def parts_list(request: Request,
                     search: str = '', type_f: str = '', cat_f: str = '',
                     show_obsolete: str = '0', msg: str = '', err: str = ''):
    include_obs = show_obsolete == '1'
    parts        = db.get_all_parts(search, type_f, cat_f, include_obsolete=include_obs)
    parent_counts = db.get_parent_counts()
    return templates.TemplateResponse("parts.html", {
        "request": request, "parts": parts,
        "search": search, "type_f": type_f, "cat_f": cat_f,
        "show_obsolete": show_obsolete,
        "types": db.TYPES, "categories": db.CATEGORIES,
        "parent_counts": parent_counts,
        "msg": msg, "err": err
    })

@app.get("/parts/new", response_class=HTMLResponse)
async def part_new_form(request: Request, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    return templates.TemplateResponse("part_form.html", {
        "request": request, "part": {}, "is_new": True,
        "types": db.TYPES, "categories": db.CATEGORIES,
        "statuses": db.PART_STATUSES, "uom_options": db.UOM_OPTIONS,
        "msg": msg, "err": err
    })

@app.get("/parts/{part_id:path}/edit", response_class=HTMLResponse)
async def part_edit_form(request: Request, part_id: str, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    part = db.get_part(part_id)
    if not part:
        return RedirectResponse(f"/parts?err=Part+not+found", 303)
    parents = db.get_bom_parents(part_id)
    return templates.TemplateResponse("part_form.html", {
        "request": request, "part": part, "is_new": False,
        "types": db.TYPES, "categories": db.CATEGORIES,
        "statuses": db.PART_STATUSES, "parents": parents,
        "uom_options": db.UOM_OPTIONS, "msg": msg, "err": err
    })

@app.post("/parts/save")
async def part_save(request: Request,
    type_: str       = Form(alias="type"), category: str   = Form(),
    base_desc: str   = Form(),             size_spec: str  = Form(''),
    variant: str     = Form(''),           plain_desc: str = Form(''),
    supplier: str    = Form(''),           brand_mfg: str  = Form(''),
    supplier_pn: str = Form(''),           uom: str        = Form('ea'),
    pkg_size: str    = Form('1'),          pkg_cost: str   = Form('0'),
    unit_cost: str   = Form('0'),          labor_hrs: str  = Form('0'),
    qty_on_hand: str = Form('0'),          status: str     = Form('ACTIVE'),
    supplier_2: str   = Form(''),          brand_mfg_2: str  = Form(''),
    supplier_pn_2: str = Form(''),         pkg_size_2: str = Form('1'),
    pkg_cost_2: str  = Form('0'),          use_alt_supplier: str = Form('0'),
    last_cost_date: str = Form(''),
    orig_part_id: str = Form('')):
    oid = orig_part_id.strip() if orig_part_id else None
    data = {
        'type': type_, 'category': category, 'base_desc': base_desc,
        'size_spec': size_spec, 'variant': variant, 'plain_desc': plain_desc,
        'supplier': supplier, 'brand_mfg': brand_mfg, 'supplier_pn': supplier_pn,
        'uom': uom, 'pkg_size': pkg_size, 'pkg_cost': pkg_cost,
        'unit_cost': unit_cost, 'labor_hrs': labor_hrs,
        'qty_on_hand': qty_on_hand, 'status': status,
        'supplier_2': supplier_2, 'brand_mfg_2': brand_mfg_2,
        'supplier_pn_2': supplier_pn_2, 'pkg_size_2': pkg_size_2,
        'pkg_cost_2': pkg_cost_2, 'use_alt_supplier': use_alt_supplier,
        'last_cost_date': last_cost_date,
    }
    if oid:
        # Check if the ID fields produce a different ID → rename first, then update fields
        candidate = db.build_part_id(type_, category, base_desc, size_spec, variant)
        if candidate and candidate != oid:
            ok_r, r_result = db.rename_part(oid, candidate)
            if not ok_r:
                return RedirectResponse(f"/parts/{oid}/edit?err={r_result}", 303)
            oid = r_result  # continue saving to new ID
        ok, result = db.upsert_part(data, orig_part_id=oid)
        if ok:
            return RedirectResponse(f"/parts/{result}/edit?msg=Saved+successfully", 303)
    else:
        ok, result = db.upsert_part(data)
        if ok:
            # Stay on new-part screen so "Save & Add Another" remains available
            return RedirectResponse(f"/parts/new?msg=Saved: {result}", 303)
    return RedirectResponse(f"/parts/new?err={result}", 303)

@app.post("/parts/{part_id:path}/delete")
async def part_delete(part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.delete_part(part_id)
    return jresp(ok, msg)

@app.post("/parts/inline-edit")
async def part_inline_edit(part_id: str = Form(), field: str = Form(), value: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.update_part_field(part_id, field, value)
    return jresp(ok, msg)

# ── BOM ────────────────────────────────────────────────────────────────────────

@app.get("/bom", response_class=HTMLResponse)
async def bom_index(request: Request, part_id: str = '', add_to: str = '',
                    msg: str = '', err: str = ''):
    assemblies  = [p for p in db.get_all_parts() if p['type'] in ('ASSY', 'FAB')]
    selected    = None
    children    = []
    tree        = None
    rolled_cost = 0.0

    bom_summary = None
    if part_id:
        selected = db.get_part(part_id)
        if selected:
            children    = db.get_bom_children(part_id)
            tree        = db.build_bom_tree(part_id)
            rolled_cost, _ = db.run_rollup(part_id)
            bom_summary = db.calc_bom_summary(part_id)

    return templates.TemplateResponse("bom.html", {
        "request": request, "assemblies": assemblies,
        "selected": selected, "children": children,
        "tree": tree, "rolled_cost": rolled_cost,
        "bom_summary": bom_summary,
        "part_id": part_id,
        "categories": db.CATEGORIES,
        "add_to": add_to,
        "msg": msg, "err": err
    })

@app.post("/bom/add")
async def bom_add(parent_id: str = Form(), child_id: str = Form(), qty: str = Form('1'), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.add_bom_row(parent_id, child_id, float(qty))
    if ok:
        db.run_rollup_for_part_and_ancestors(parent_id)
    return jresp(ok, msg)

@app.post("/bom/update-qty")
async def bom_update_qty(parent_id: str = Form(), child_id: str = Form(), qty: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.update_bom_qty(parent_id, child_id, float(qty))
    if ok:
        db.run_rollup_for_part_and_ancestors(parent_id)
    return jresp(ok, msg)

@app.post("/bom/update-labor")
async def bom_update_labor(part_id: str = Form(), labor_hrs: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    """Update labor_hrs from the BOM editor — also triggers ancestor rollup."""
    ok, msg = db.update_part_labor(part_id, float(labor_hrs))
    if ok:
        db.run_rollup_for_part_and_ancestors(part_id)
    return jresp(ok, msg)

@app.post("/bom/remove")
async def bom_remove(parent_id: str = Form(), child_id: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.delete_bom_row(parent_id, child_id)
    if ok:
        db.run_rollup_for_part_and_ancestors(parent_id)
    return jresp(ok, msg)

@app.post("/bom/reorder")
async def bom_reorder(parent_id: str = Form(), order: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    """Receive JSON array of child_ids in new order."""
    try:
        ordered = json.loads(order)
    except Exception:
        return jresp(False, "Invalid order data.")
    ok, msg = db.reorder_bom(parent_id, ordered)
    return jresp(ok, msg)

@app.post("/bom/rollup-all")
async def bom_rollup_all(labor_rate: float = Form(25.0), db_conn: sqlite3.Connection = Depends(get_db)):
    # labor_rate param kept for JS compatibility but no longer passed to rollup
    db.rollup_all()
    return jresp(True, "All costs rolled up successfully.")

@app.get("/bom/tree/{part_id:path}")
async def bom_tree_json(part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    return JSONResponse(db.build_bom_tree(part_id))

@app.get("/api/bom/explode/{part_id:path}")
async def bom_explode_json(part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    """Flat exploded BOM for the order sheet modal — deduped, with supplier info."""
    rows = db.explode_bom_flat_deduped(part_id)
    return JSONResponse(rows)

# ── Projects ───────────────────────────────────────────────────────────────────

@app.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    projects = db.get_all_projects_with_summary()
    return templates.TemplateResponse("projects.html", {
        "request": request, "projects": projects, "msg": msg, "err": err
    })

@app.get("/projects/new", response_class=HTMLResponse)
async def project_new(request: Request, db_conn: sqlite3.Connection = Depends(get_db)):
    return templates.TemplateResponse("project_form.html", {
        "request": request, "project": {}, "is_new": True
    })

@app.get("/projects/{project_id}/edit", response_class=HTMLResponse)
async def project_edit(request: Request, project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    project = db.get_project(project_id)
    if not project:
        return RedirectResponse("/projects?err=Not+found", 303)
    return templates.TemplateResponse("project_form.html", {
        "request": request, "project": project, "is_new": False
    })

@app.post("/projects/save")
async def project_save(
    project_id: str  = Form(), status: str    = Form('ACTIVE'),
    customer: str    = Form(''), notes: str   = Form(''),
    labor_rate: str  = Form('25'), markup: str = Form('0')):
    ok, result = db.upsert_project({
        'project_id': project_id, 'status': status, 'customer': customer,
        'notes': notes, 'labor_rate': labor_rate, 'markup': markup
    })
    if ok:
        return RedirectResponse(f"/projects/{result}", 303)
    return RedirectResponse(f"/projects/new?err={result}", 303)

@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    summary = db.get_project_summary(project_id)
    if not summary:
        return RedirectResponse("/projects?err=Not+found", 303)
    return templates.TemplateResponse("project_detail.html", {
        "request": request, **summary,
        "item_types": getattr(db, 'ITEM_TYPES', ['STANDARD', 'OPTION', 'ADDITIONAL', 'DELETED']),
        "boxes": db.get_project_boxes(project_id),
        "pallets": db.get_project_pallets(project_id),
        "other_items": db.get_project_other_items(project_id),
        "optional_items": db.get_project_optional_items(project_id),
        "msg": msg, "err": err
    })

@app.post("/projects/{project_id}/add-item")
async def project_add_item(project_id: str, part_id: str = Form(), qty: str = Form('1'), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.add_project_item(project_id, part_id, float(qty))
    if not ok:
        return jresp(ok, msg)
    # Return new item id for type-setting
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM project_items WHERE project_id=? AND part_id=? ORDER BY id DESC LIMIT 1",
            (project_id, part_id)
        ).fetchone()
    item_id = row[0] if row else None
    return jresp(True, msg, item_id=item_id)

@app.post("/projects/item/update")
async def project_item_update(
    item_id: int = Form(), qty: str = Form(None), picked: str = Form(None), box_num: str = Form(None),
    discount_pct: str = Form(None), discount_flat: str = Form(None)):
    ok, msg = db.update_project_item(
        item_id,
        qty    = float(qty)  if qty    is not None else None,
        picked = int(picked) if picked is not None else None,
        box_num=box_num,
        discount_pct = float(discount_pct) if discount_pct is not None else None,
        discount_flat = float(discount_flat) if discount_flat is not None else None
    )
    return jresp(ok, msg)

@app.post("/projects/{project_id}/other-items/add")
async def other_item_add(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    ok, result = db.add_project_other_item(project_id)
    return jresp(ok, "Added" if ok else str(result), id=result if ok else None)

@app.post("/projects/other-item/update")
async def other_item_update(item_id: int = Form(), field: str = Form(), value: str = Form(None), db_conn: sqlite3.Connection = Depends(get_db)):
    allowed = {'description','cost','labor_hrs','apply_markup','box_num',
               'discount_pct','discount_flat','show_on_proforma'}
    if field not in allowed:
        return jresp(False, f"Field '{field}' not editable")
    # Type coerce
    if field in ('cost','labor_hrs','discount_pct','discount_flat'):
        val = float(value or 0)
    elif field in ('apply_markup','show_on_proforma'):
        val = int(value or 0)
    else:
        val = value or ''
    ok, msg = db.update_project_other_item(item_id, **{field: val})
    return jresp(ok, msg)

@app.post("/projects/other-item/delete")
async def other_item_delete(item_id: int = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.delete_project_other_item(item_id)
    return jresp(ok, msg)

@app.post("/projects/{project_id}/packing/save")
async def project_packing_save(project_id: str, request: Request, db_conn: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    boxes = data.get("boxes", [])
    pallets = data.get("pallets", [])
    ok, msg = db.save_project_packing(project_id, boxes, pallets)
    return jresp(ok, msg)

@app.post("/projects/item/delete")
async def project_item_delete(item_id: int = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.delete_project_item(item_id)
    return jresp(ok, msg)

@app.post("/projects/{project_id}/delete")
async def project_delete(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.delete_project(project_id)
    return jresp(ok, msg)


# ── Project clone ─────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/clone")
async def project_clone(project_id: str, new_id: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, result = db.clone_project(project_id, new_id)
    return jresp(ok, f"Cloned to {result}" if ok else result, new_id=result if ok else None)


# ── Part rename ───────────────────────────────────────────────────────────────

@app.post("/parts/rename")
async def part_rename(old_id: str = Form(), new_id: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, result = db.rename_part(old_id, new_id)
    if ok:
        return RedirectResponse(f"/parts/{result}/edit?msg=Part+renamed+successfully", 303)
    return RedirectResponse(f"/parts/{old_id}/edit?err={result}", 303)



@app.get("/api/parts/field-values")
async def api_field_values(db_conn: sqlite3.Connection = Depends(get_db)):
    return db.get_part_field_values()

@app.get("/api/project-parts/{project_id}")
async def api_project_parts(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    ids = db.get_project_part_ids(project_id)
    return list(ids)

# ── Audit log ──────────────────────────────────────────────────────────────────

@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request,
                     entity_type: str = '', entity_id: str = '',
                     user: str = '', date_from: str = '', date_to: str = '',
                     offset: int = 0):
    PAGE = 100
    rows  = db.get_change_log(
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        user=user or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=PAGE + 1, offset=offset
    )
    has_more = len(rows) > PAGE
    rows     = rows[:PAGE]
    users    = db.get_change_log_users()
    return templates.TemplateResponse("audit.html", {
        "request": request, "rows": rows, "users": users,
        "f_entity_type": entity_type, "f_entity_id": entity_id,
        "f_user": user, "f_date_from": date_from, "f_date_to": date_to,
        "offset": offset, "page": PAGE, "has_more": has_more,
    })

@app.get("/api/audit/export")
async def audit_export(entity_type: str = '', entity_id: str = '',
                       user: str = '', date_from: str = '', date_to: str = ''):
    rows = db.get_change_log(
        entity_type=entity_type or None, entity_id=entity_id or None,
        user=user or None, date_from=date_from or None, date_to=date_to or None,
        limit=10000, offset=0
    )
    import io as _io
    buf = _io.StringIO()
    buf.write("timestamp,user,entity_type,entity_id,action,field,old_val,new_val\n")
    for r in rows:
        buf.write(','.join(f'"{str(r.get(c,"") or "").replace(chr(34), chr(39))}"'
                           for c in ['ts','user','entity_type','entity_id',
                                     'action','field','old_val','new_val']) + '\n')
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lems_audit.csv"}
    )

# ── Admin / Import ─────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {
        "request": request, "msg": msg, "err": err
    })

@app.post("/admin/import-csv")
async def admin_import_csv(file: UploadFile = File(...), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, content = await _read_upload(file)
    if not ok:
        return jresp(False, content)
    text    = content.decode('utf-8-sig', errors='replace')
    reader  = csv.DictReader(io.StringIO(text))
    results = db.import_from_csv_data(list(reader))
    db.rollup_all()
    return jresp(True, "CSV import complete.", results=results)

@app.post("/admin/import-master")
async def admin_import_master(file: UploadFile = File(...), db_conn: sqlite3.Connection = Depends(get_db)):
    """Full-replace master data import — wipes all parts+BOM before loading."""
    ok, content = await _read_upload(file)
    if not ok:
        return jresp(False, content)
    text    = content.decode('utf-8-sig', errors='replace')
    reader  = csv.DictReader(io.StringIO(text))
    results = db.import_master_data(list(reader))
    db.rollup_all()
    return jresp(True, "Master data replace complete.", results=results)

@app.post("/admin/import-db")
async def admin_import_db(file: UploadFile = File(...), db_conn: sqlite3.Connection = Depends(get_db)):
    """Import from a .db SQLite file directly."""
    ok, content = await _read_upload(file)
    if not ok:
        return jresp(False, content)
    os.makedirs(UPLOAD_TMP, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.db', dir=UPLOAD_TMP, delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        results = db.import_from_sqlite(tmp_path)
        db.rollup_all()
    finally:
        try: os.remove(tmp_path)
        except Exception: pass
    return jresp(True, "DB import complete.", results=results)

@app.post("/admin/import-xlsx")
async def admin_import_xlsx(file: UploadFile = File(...), db_conn: sqlite3.Connection = Depends(get_db)):
    """Import from a .xlsx workbook."""
    ok, content = await _read_upload(file)
    if not ok:
        return jresp(False, content)
    os.makedirs(UPLOAD_TMP, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.xlsx', dir=UPLOAD_TMP, delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        results = db.import_from_xlsx(tmp_path)
        db.rollup_all()
    finally:
        try: os.remove(tmp_path)
        except Exception: pass
    return jresp(True, "XLSX import complete.", results=results)

@app.get("/admin/export-csv")
async def admin_export_csv(db_conn: sqlite3.Connection = Depends(get_db)):
    output     = io.StringIO()
    fieldnames = [
        # Parts
        '_table','part_id','type','category','base_desc','size_spec','variant',
        'plain_desc','supplier','uom','qty_on_hand','unit_cost','cost','brand_mfg',
        'supplier_pn','pkg_size','pkg_cost','labor_hrs','on_hand','status',
        'supplier_2','brand_mfg_2','supplier_pn_2','pkg_size_2','pkg_cost_2',
        'unit_cost_2','use_alt_supplier','last_cost_date',
        # BOM
        'parent_id','child_id','qty',
        # Projects
        'project_id','proj_status','customer','notes','labor_rate','markup',
        # Project items
        'picked','item_type','box_num','discount_pct','discount_flat',
        # Packing
        'weight','pallet_num','dimensions',
        # Other/quoted items
        'description','labor_hrs','apply_markup','show_on_proforma','sort_order',
        # Quote
        'version','quote_status','currency','overhead_rate','markup_pct',
        'freight_inbound','freight_outbound','cal_gases_cost','cal_gases_freight',
        'training_days','training_cost','training_notes',
        'discount_note','internal_notes','proforma_header','proforma_footer',
        'other_items',
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    with db.get_conn() as conn:
        for p in conn.execute("SELECT * FROM parts ORDER BY part_id").fetchall():
            row = dict(p); row['_table'] = 'PART'; writer.writerow(row)
        for b in conn.execute("SELECT * FROM bom ORDER BY parent_id,sort_order").fetchall():
            writer.writerow({'_table':'BOM','parent_id':b['parent_id'],
                             'child_id':b['child_id'],'qty':b['qty']})
        for proj in conn.execute("SELECT * FROM projects").fetchall():
            p = dict(proj); p['_table'] = 'PROJ'
            p['proj_status'] = p.pop('status', '')
            writer.writerow(p)
        for pi in conn.execute(
            """SELECT id, project_id, part_id, qty, picked, item_type,
               COALESCE(box_num,'') as box_num,
               COALESCE(discount_pct,0) as discount_pct,
               COALESCE(discount_flat,0) as discount_flat
               FROM project_items"""
        ).fetchall():
            row = dict(pi); row['_table'] = 'P_ITEM'; writer.writerow(row)
        for b in conn.execute("SELECT * FROM project_boxes").fetchall():
            row = dict(b); row['_table'] = 'P_BOX'; writer.writerow(row)
        for p in conn.execute("SELECT * FROM project_pallets").fetchall():
            row = dict(p); row['_table'] = 'P_PALLET'; writer.writerow(row)
        for q in conn.execute("SELECT * FROM project_quotes").fetchall():
            row = dict(q); row['_table'] = 'P_QUOTE'
            row['quote_status'] = row.pop('status', 'DRAFT')
            writer.writerow(row)
        for oi in conn.execute("SELECT * FROM project_other_items ORDER BY project_id, sort_order").fetchall():
            row = dict(oi); row['_table'] = 'P_OTHER'; writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lems_backup.csv"}
    )

# ── Quotes ────────────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/quote", response_class=HTMLResponse)
async def project_quote(request: Request, project_id: str, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    project = db.get_project(project_id)
    if not project:
        return RedirectResponse("/projects?err=Not+found", 303)
    summary = db.get_project_summary(project_id)
    quote   = db.get_or_create_quote(project_id)

    other_items   = db.get_project_other_items(project_id)
    totals = calculations.compute_quote_totals(project, summary, quote, other_items)

    db.save_quote_totals(project_id, totals['quoted_total'], totals['gross_margin_pct'], totals['total_internal'])
    quote['markup_pct'] = totals['markup_pct']

    return templates.TemplateResponse("project_quote.html", {
        "request": request, "project": project, "quote": quote,
        **totals,
        "other_items": other_items, "msg": msg, "err": err,
    })

@app.post("/projects/{project_id}/quote/save")
async def quote_save(project_id: str, request: Request, db_conn: sqlite3.Connection = Depends(get_db)):
    form = await request.form()
    data = dict(form)

    # other_items now live in project_other_items table — nothing to collect from form
    data["other_items"] = []  # keep field for save_quote compat, no longer used

    project = db.get_project(project_id)
    summary = db.get_project_summary(project_id)
    other_items = db.get_project_other_items(project_id)

    totals = calculations.compute_quote_totals(project, summary, data, other_items)

    data['quoted_total']     = totals['quoted_total']
    data['gross_margin_pct'] = totals['gross_margin_pct']
    data['labor_rate_quoted'] = totals['labor_rate_quoted']
    data['total_internal']   = totals['total_internal']

    ok, msg = db.save_quote(project_id, data)
    if ok:
        proj = db.get_project(project_id)
        if proj:
            db.upsert_project({**proj, 'markup': float(data.get('markup_pct') or 0)})
    if ok:
        return RedirectResponse(f"/projects/{project_id}/quote?msg=Quote+saved", 303)
    return RedirectResponse(f"/projects/{project_id}/quote?err={msg}", 303)

@app.post("/projects/{project_id}/quote/preview")
async def quote_preview(project_id: str, request: Request, db_conn: sqlite3.Connection = Depends(get_db)):
    """Return live calculation totals without saving anything.
    The JS recalcTotals() debounce calls this so the browser never does its
    own math — calculations.py remains the Single Source of Truth."""
    project = db.get_project(project_id)
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    form        = await request.form()
    saved_quote = db.get_or_create_quote(project_id)
    summary     = db.get_project_summary(project_id)
    other_items = db.get_project_other_items(project_id)

    # Build quote dict: start from DB (preserves frozen state, other_items, etc.)
    # then layer in whatever the user has currently typed in the form.
    preview_quote = {
        **saved_quote,
        "overhead_rate":     form.get("overhead_rate",     saved_quote.get("overhead_rate",     1.0)),
        "labor_rate_quoted": form.get("labor_rate_quoted", saved_quote.get("labor_rate_quoted", 0)),
        "markup_pct":        form.get("markup_pct",        saved_quote.get("markup_pct",        0)),
        "freight_inbound":   form.get("freight_inbound",   saved_quote.get("freight_inbound",   0)),
        "freight_outbound":  form.get("freight_outbound",  saved_quote.get("freight_outbound",  0)),
        "cal_gases_cost":    form.get("cal_gases_cost",    saved_quote.get("cal_gases_cost",    0)),
        "cal_gases_freight": form.get("cal_gases_freight", saved_quote.get("cal_gases_freight", 0)),
        "training_cost":     form.get("training_cost",     saved_quote.get("training_cost",     0)),
        "discount_pct":      form.get("discount_pct",      saved_quote.get("discount_pct",      0)),
        "discount_flat":     form.get("discount_flat",     saved_quote.get("discount_flat",     0)),
    }

    totals = calculations.compute_quote_totals(project, summary, preview_quote, other_items)

    return JSONResponse({k: round(v, 2) if isinstance(v, float) else v
                         for k, v in totals.items() if not isinstance(v, list)})


@app.post("/projects/{project_id}/quote/freeze")
async def quote_freeze(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    summary = db.get_project_summary(project_id)
    if not summary:
        return jresp(False, "Project not found")
    ok, msg = db.save_quote(project_id, {
        **db.get_or_create_quote(project_id),
        "frozen_material":  summary.get("total_material", 0),
        "frozen_labor_hrs": summary.get("total_labor_hrs", 0),
        "costs_frozen": 1,
        "frozen_at": datetime.datetime.now().isoformat(timespec='seconds'),
    })
    return jresp(ok, "Costs frozen at current values." if ok else msg)

@app.post("/projects/{project_id}/quote/unfreeze")
async def quote_unfreeze(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.save_quote(project_id, {
        **db.get_or_create_quote(project_id),
        "costs_frozen": 0, "frozen_at": "",
    })
    return jresp(ok, "Costs unfrozen — live BOM values will be used." if ok else msg)

@app.post("/projects/{project_id}/quote/bump-version")
async def quote_bump_version(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    v = db.increment_quote_version(project_id)
    return jresp(True, f"Version bumped to v{v}.", version=v)

# ── API ────────────────────────────────────────────────────────────────────────

@app.get("/api/parts/search")
async def api_parts_search(q: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    parts = db.get_all_parts(search=q)
    return JSONResponse([{
        'part_id': p['part_id'], 'plain_desc': p['plain_desc'],
        'type': p['type'], 'unit_cost': p['unit_cost'], 'uom': p['uom'],
    } for p in parts[:60]])

@app.get("/api/parts/{part_id:path}/cost-history")
async def api_part_cost_history(part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    history = db.get_part_cost_history(part_id)
    return JSONResponse(history)

# ── Attachments ───────────────────────────────────────────────────────────────

import uuid

@app.post("/api/parts/{part_id:path}/attachments")
async def api_upload_attachment(part_id: str, file: UploadFile = File(...), request: Request = None, db_conn: sqlite3.Connection = Depends(get_db)):
    ok, content = await _read_upload(file)
    if not ok: return jresp(False, content)
    
    att_id = str(uuid.uuid4())
    filename = f"{att_id}_{file.filename}"
    filepath = os.path.join(ATTACHMENTS_DIR, filename)
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    user = db.get_current_user()
    db.add_part_attachment({
        'id': att_id,
        'part_id': part_id,
        'filename': filename,
        'original_filename': file.filename,
        'mime_type': file.content_type,
        'size_bytes': len(content),
        'uploaded_by': user
    })
    return jresp(True, "Uploaded", id=att_id)

@app.get("/api/parts/{part_id:path}/attachments")
async def api_get_part_attachments(part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    return JSONResponse(db.get_part_attachments(part_id))

@app.get("/api/projects/{project_id:path}/attachments")
async def api_get_project_attachments(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    return JSONResponse(db.get_project_attachments(project_id))

@app.delete("/api/attachments/{att_id}")
async def api_delete_attachment(att_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    row = db.delete_part_attachment(att_id)
    if not row: return jresp(False, "Not found")
    filepath = os.path.join(ATTACHMENTS_DIR, row['filename'])
    if os.path.exists(filepath): os.remove(filepath)
    return jresp(True, "Deleted")

@app.get("/attachments/{att_id}")
async def serve_attachment(att_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM part_attachments WHERE id=?", (att_id,)).fetchone()
        if not row: return HTMLResponse("Not found", 404)
        filepath = os.path.join(ATTACHMENTS_DIR, row['filename'])
        if not os.path.exists(filepath): return HTMLResponse("File missing", 404)
        return FileResponse(filepath, filename=row['original_filename'])

# ── Run ────────────────────────────────────────────────────────────────────────

def open_browser():
    import time; time.sleep(1.2)
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    import os
    # Set LEMS_HOST=0.0.0.0 in the launcher script to expose to the local network.
    # Defaults to 127.0.0.1 (localhost only) for dev/PyCharm use.
    host = os.environ.get("LEMS_HOST", "127.0.0.1")
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("main:app", host=host, port=8000, reload=False)

# ── Where-used ────────────────────────────────────────────────────────────────

@app.get("/parts/{part_id:path}/where-used", response_class=HTMLResponse)
async def where_used(request: Request, part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    part = db.get_part(part_id)
    if not part:
        return RedirectResponse("/parts?err=Part+not+found", 303)
    usages   = db.get_where_used(part_id)
    direct   = db.get_direct_parents(part_id)
    return templates.TemplateResponse("where_used.html", {
        "request": request, "part": part,
        "usages": usages, "direct": direct,
    })

# ── Print / PDF ───────────────────────────────────────────────────────────────

@app.get("/print/project/{project_id}", response_class=HTMLResponse)
async def print_project(request: Request, project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    data = db.build_print_project(project_id)
    if not data:
        return RedirectResponse("/projects?err=Not+found", 303)
    return templates.TemplateResponse("print_project.html", {
        "request": request, **data,
        "boxes": db.get_project_boxes(project_id),
        "pallets": db.get_project_pallets(project_id)
    })

@app.get("/parts/{part_id}/bom", response_class=HTMLResponse)
async def part_bom_print(request: Request, part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    part = db.get_part(part_id)
    if not part:
        return RedirectResponse("/parts", 303)

    # Run rollup to ensure costs are fresh before viewing BOM
    rolled_cost, _ = db.run_rollup(part_id)
    tree        = db.build_bom_tree(part_id)
    flat        = db.explode_bom_flat_deduped(part_id)
    bom_summary = db.calc_bom_summary(part_id)
    return templates.TemplateResponse("print_bom.html", {
        "request": request, "part": part,
        "tree": tree, "rolled_cost": rolled_cost, "flat": flat,
        "bom_summary": bom_summary,
    })

@app.get("/print/bom/{part_id:path}", response_class=HTMLResponse)
async def print_bom(request: Request, part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    part = db.get_part(part_id)
    if not part:
        return RedirectResponse("/bom?err=Not+found", 303)
    tree        = db.build_bom_tree(part_id)
    rolled_cost, _ = db.run_rollup(part_id)
    flat        = db.explode_bom_flat_deduped(part_id)
    bom_summary = db.calc_bom_summary(part_id)
    return templates.TemplateResponse("print_bom.html", {
        "request": request, "part": part,
        "tree": tree, "rolled_cost": rolled_cost, "flat": flat,
        "bom_summary": bom_summary,
    })

# ── Pick list ─────────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/pick-list", response_class=HTMLResponse)
async def pick_list(request: Request, project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):
    project  = db.get_project(project_id)
    if not project:
        return RedirectResponse("/projects?err=Not+found", 303)
    pick     = db.generate_pick_list(project_id)
    shortage = [p for p in pick if p['shortage'] > 0]
    total    = sum(p['ext_cost'] for p in pick)
    return templates.TemplateResponse("pick_list.html", {
        "request": request, "project": project,
        "pick": pick, "shortage": shortage, "total": total,
    })

@app.post("/projects/{project_id}/pick-list/commit")
async def pick_list_commit(project_id: str, request: Request, db_conn: sqlite3.Connection = Depends(get_db)):
    """Persist picks and deduct qty from on-hand inventory."""
    data = await request.json()
    picks = data.get('picks', [])  # [{part_id, qty}, ...]
    ok, msg = db.commit_picks(project_id, picks)
    return jresp(ok, msg)

@app.post("/projects/{project_id}/pick-list/unpick")
async def pick_list_unpick(project_id: str, part_id: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    """Return a single picked item to inventory."""
    ok, msg = db.commit_picks(project_id, [{'part_id': part_id, 'qty': 0}])
    return jresp(ok, msg)

# ── Inventory ─────────────────────────────────────────────────────────────────

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request, msg: str = '', err: str = '', db_conn: sqlite3.Connection = Depends(get_db)):
    parts       = db.get_inventory_list()
    projects    = db.get_all_projects()
    global_need = db.get_global_need()
    return templates.TemplateResponse("inventory.html", {
        "request": request, "parts": parts, "projects": projects,
        "categories": db.CATEGORIES,
        "global_need":      global_need,
        "global_need_json": json.dumps(global_need),
        "msg": msg, "err": err,
    })

@app.post("/inventory/update")
async def inventory_update(
    part_id: str      = Form(),
    qty_on_hand: str  = Form(None),
    qty_on_order: str = Form(None),
    order_eta: str    = Form(None)):
    ok, msg = db.update_inventory(
        part_id,
        qty_on_hand  = float(qty_on_hand)  if qty_on_hand  not in (None,'') else None,
        qty_on_order = float(qty_on_order) if qty_on_order not in (None,'') else None,
        order_eta    = order_eta           if order_eta    not in (None,'') else None,
    )
    return jresp(ok, msg)

# ── Project item type ─────────────────────────────────────────────────────────

@app.post("/projects/item/set-type")
async def project_item_set_type(item_id: int = Form(), item_type: str = Form(), db_conn: sqlite3.Connection = Depends(get_db)):
    ok, msg = db.set_project_item_type(item_id, item_type)
    return jresp(ok, msg)

# ── Project inline metadata edit ──────────────────────────────────────────────

@app.post("/projects/{project_id}/inline-edit")
async def project_inline_edit(project_id: str,
                               field: str = Form(), value: str = Form()):
    safe = {'customer', 'status', 'labor_rate', 'markup', 'notes'}
    if field not in safe:
        return jresp(False, f"Field '{field}' not editable.")
    with db.get_conn() as conn:
        conn.execute(f"UPDATE projects SET {field}=? WHERE project_id=?",
                     (value, project_id))
    # Auto-rollup when labor_rate or markup changes (affects line totals)
    if field in ('labor_rate', 'markup'):
        db.rollup_all()
    return jresp(True, "Saved.")

# ── Flags API (for admin page) ────────────────────────────────────────────────

@app.get("/api/flags")
async def api_flags(db_conn: sqlite3.Connection = Depends(get_db)):
    flags = db.get_system_flags()
    counts = {k: len(v) for k, v in flags.items()}
    total  = sum(counts.values())
    return JSONResponse({"flags": flags, "counts": counts, "total": total})
