import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

import database as db
from main import app, ATTACHMENTS_DIR

client = TestClient(app)

def setup_module(module):
    # Ensure test database starts clean
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.init_db()

    # Create dummy part
    with db.get_conn() as conn:
        db._upsert_part_row(conn, {'part_id': 'TEST-PART-1', 'type': 'PRT', 'category': 'HARDWARE', 'base_desc': 'TEST'})

def test_upload_and_list_attachment():
    # 1. Upload a dummy text file
    file_content = b"Hello, this is a test drawing."
    files = {'file': ('drawing.txt', file_content, 'text/plain')}
    
    res = client.post("/api/parts/TEST-PART-1/attachments", files=files, cookies={"lems_user": "test_runner"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    att_id = data["id"]
    
    # 2. List attachments for part
    res2 = client.get("/api/parts/TEST-PART-1/attachments", cookies={"lems_user": "test_runner"})
    assert res2.status_code == 200
    atts = res2.json()
    assert len(atts) == 1
    assert atts[0]["id"] == att_id
    assert atts[0]["original_filename"] == "drawing.txt"
    assert atts[0]["size_bytes"] == len(file_content)

    # 3. Verify file exists on disk
    filepath = os.path.join(ATTACHMENTS_DIR, atts[0]["filename"])
    assert os.path.exists(filepath)
    with open(filepath, "rb") as f:
        assert f.read() == file_content

    # 4. Download endpoint
    res3 = client.get(f"/attachments/{att_id}", cookies={"lems_user": "test_runner"})
    assert res3.status_code == 200
    assert res3.content == file_content

    # 5. Delete attachment
    res4 = client.delete(f"/api/attachments/{att_id}", cookies={"lems_user": "test_runner"})
    assert res4.status_code == 200
    assert res4.json()["ok"] is True

    # 6. Verify file removed from disk and DB
    assert not os.path.exists(filepath)
    res5 = client.get("/api/parts/TEST-PART-1/attachments", cookies={"lems_user": "test_runner"})
    assert len(res5.json()) == 0
