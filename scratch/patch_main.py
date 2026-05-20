import sys
import os

def patch_main():
    with open("main.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 1. Add attachments directory creation
        if line.startswith("UPLOAD_TMP"):
            out.append(line)
            out.append("ATTACHMENTS_DIR = os.path.join(os.path.dirname(__file__), \"attachments\")\n")
            out.append("os.makedirs(ATTACHMENTS_DIR, exist_ok=True)\n")
            i += 1
            continue
            
        # 2. Add API endpoints
        if line.startswith("def api_part_cost_history"):
            # include the function
            out.append(line)
            i += 1
            while i < len(lines) and (lines[i].startswith("    ") or lines[i].strip() == ""):
                out.append(lines[i])
                i += 1
            
            # Now insert our new endpoints
            out.append("\n")
            out.append("import uuid\n")
            out.append("@app.post(\"/api/parts/{part_id:path}/attachments\")\n")
            out.append("async def api_upload_attachment(part_id: str, file: UploadFile = File(...), request: Request = None, db_conn: sqlite3.Connection = Depends(get_db)):\n")
            out.append("    ok, content = await _read_upload(file)\n")
            out.append("    if not ok: return jresp(False, content)\n")
            out.append("    \n")
            out.append("    att_id = str(uuid.uuid4())\n")
            out.append("    filename = f\"{att_id}_{file.filename}\"\n")
            out.append("    filepath = os.path.join(ATTACHMENTS_DIR, filename)\n")
            out.append("    \n")
            out.append("    with open(filepath, \"wb\") as f:\n")
            out.append("        f.write(content)\n")
            out.append("    \n")
            out.append("    user = db.get_current_user()\n")
            out.append("    db.add_part_attachment({\n")
            out.append("        'id': att_id,\n")
            out.append("        'part_id': part_id,\n")
            out.append("        'filename': filename,\n")
            out.append("        'original_filename': file.filename,\n")
            out.append("        'mime_type': file.content_type,\n")
            out.append("        'size_bytes': len(content),\n")
            out.append("        'uploaded_by': user\n")
            out.append("    })\n")
            out.append("    return jresp(True, \"Uploaded\", id=att_id)\n\n")

            out.append("@app.get(\"/api/parts/{part_id:path}/attachments\")\n")
            out.append("async def api_get_part_attachments(part_id: str, db_conn: sqlite3.Connection = Depends(get_db)):\n")
            out.append("    return JSONResponse(db.get_part_attachments(part_id))\n\n")

            out.append("@app.get(\"/api/projects/{project_id:path}/attachments\")\n")
            out.append("async def api_get_project_attachments(project_id: str, db_conn: sqlite3.Connection = Depends(get_db)):\n")
            out.append("    return JSONResponse(db.get_project_attachments(project_id))\n\n")

            out.append("@app.delete(\"/api/attachments/{att_id}\")\n")
            out.append("async def api_delete_attachment(att_id: str, db_conn: sqlite3.Connection = Depends(get_db)):\n")
            out.append("    row = db.delete_part_attachment(att_id)\n")
            out.append("    if not row: return jresp(False, \"Not found\")\n")
            out.append("    filepath = os.path.join(ATTACHMENTS_DIR, row['filename'])\n")
            out.append("    if os.path.exists(filepath): os.remove(filepath)\n")
            out.append("    return jresp(True, \"Deleted\")\n\n")

            out.append("@app.get(\"/attachments/{att_id}\")\n")
            out.append("async def serve_attachment(att_id: str, db_conn: sqlite3.Connection = Depends(get_db)):\n")
            out.append("    with db.get_conn() as conn:\n")
            out.append("        row = conn.execute(\"SELECT * FROM part_attachments WHERE id=?\", (att_id,)).fetchone()\n")
            out.append("        if not row: return HTMLResponse(\"Not found\", 404)\n")
            out.append("        filepath = os.path.join(ATTACHMENTS_DIR, row['filename'])\n")
            out.append("        if not os.path.exists(filepath): return HTMLResponse(\"File missing\", 404)\n")
            out.append("        return FileResponse(filepath, filename=row['original_filename'])\n\n")
            continue
            
        out.append(line)
        i += 1

    with open("main.py", "w", encoding="utf-8") as f:
        f.writelines(out)

if __name__ == "__main__":
    patch_main()
