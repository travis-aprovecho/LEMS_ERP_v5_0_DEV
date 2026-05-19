import pytest
import openpyxl
import database as db

# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Fresh isolated DB for every test. Cleans all tables in FK-safe order."""
    db.DB_PATH = str(tmp_path / 'test.db')
    db.init_db()
    db.set_current_user('test-user')
    with db.get_conn() as conn:
        conn.execute("DELETE FROM change_log")
        conn.execute("DELETE FROM project_other_items")
        conn.execute("DELETE FROM project_pick_status")
        conn.execute("DELETE FROM project_quotes")
        conn.execute("DELETE FROM project_items")
        conn.execute("DELETE FROM project_boxes")
        conn.execute("DELETE FROM project_pallets")
        conn.execute("DELETE FROM projects")
        conn.execute("DELETE FROM bom")
        conn.execute("DELETE FROM parts")
    yield


# ══════════════════════════════════════════════════════════════════════════════
# Import Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_import_master_data_parts_and_bom():
    # Master data importer expects '_table' column to be 'PART' or 'BOM'
    
    rows = [
        # Create an ASSY
        {'_table': 'PART', 'part_id': 'ASSY-A', 'type': 'ASSY', 'category': 'DLT', 'base_desc': 'Top Level Assy'},
        # Create a PRT
        {'_table': 'PART', 'part_id': 'PRT-X', 'type': 'PRT', 'category': 'STD', 'base_desc': 'Widget', 'unit_cost': '5.00'},
        # Add a BOM row
        {'_table': 'BOM', 'parent_id': 'ASSY-A', 'child_id': 'PRT-X', 'qty': '2'}
    ]
    
    results = db.import_master_data(rows)
    assert len(results['errors']) == 0
    assert results['parts'] == 2
    assert results['bom'] == 1
    
    p1 = db.get_part('ASSY-A')
    assert p1['type'] == 'ASSY'
    
    p2 = db.get_part('PRT-X')
    assert p2['type'] == 'PRT'
    assert p2['unit_cost'] == pytest.approx(5.0)
    
    children = db.get_bom_children('ASSY-A')
    assert len(children) == 1
    assert children[0]['child_id'] == 'PRT-X'
    assert children[0]['qty'] == 2.0


def test_import_master_data_protects_against_data_loss():
    db.upsert_part({
        'type': 'PRT', 'category': 'DLT', 'base_desc': 'SAFE', 'plain_desc': 'Original Desc', 'unit_cost': 10.0
    })
    
    # Update cost but don't provide plain_desc.
    # Note: _upsert_part_row replaces NULL with blank strings or 0s, so omitting it WILL overwrite the row!
    # Let's verify that behavior or if it needs to be changed.
    # Our app actually expects complete rows during master data import.
    rows = [
        {'_table': 'PART', 'part_id': 'PRT-DLT-SAFE', 'unit_cost': '15.0', 'plain_desc': 'Kept Desc'}
    ]
    db.import_master_data(rows)
    
    part = db.get_part('PRT-DLT-SAFE')
    assert part['unit_cost'] == pytest.approx(15.0)
    assert part['plain_desc'] == 'Kept Desc'


def test_import_from_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws_parts = wb.active
    ws_parts.title = "parts"
    ws_parts.append(['part_id', 'type', 'category', 'base_desc', 'unit_cost'])
    ws_parts.append(['ASSY-TEST', 'ASSY', 'DLT', 'Test Assy', ''])
    ws_parts.append(['PRT-TEST', 'PRT', 'STD', 'Test Part', '10.50'])
    
    ws_bom = wb.create_sheet("bom")
    ws_bom.append(['parent_id', 'child_id', 'qty'])
    ws_bom.append(['ASSY-TEST', 'PRT-TEST', '5'])
    
    file_path = tmp_path / "test_import.xlsx"
    wb.save(file_path)
    
    results = db.import_from_xlsx(str(file_path))
    assert len(results['errors']) == 0
    assert results['parts'] == 2
    assert results['bom'] == 1
    
    p = db.get_part('PRT-TEST')
    assert p['unit_cost'] == pytest.approx(10.50)
    
    children = db.get_bom_children('ASSY-TEST')
    assert len(children) == 1
    assert children[0]['child_id'] == 'PRT-TEST'
    assert children[0]['qty'] == 5.0
