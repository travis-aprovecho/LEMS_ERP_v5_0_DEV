import pytest
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


def _insert_parts(conn, *parts):
    """Helper: insert (part_id, type, unit_cost=0, labor_hrs=0) tuples."""
    for p in parts:
        pid, ptype = p[0], p[1]
        cost  = p[2] if len(p) > 2 else 0
        labor = p[3] if len(p) > 3 else 0
        conn.execute(
            "INSERT INTO parts (part_id, type, category, base_desc, unit_cost, labor_hrs) "
            "VALUES (?,?,?,?,?,?)",
            (pid, ptype, 'cat', 'desc', cost, labor)
        )


# ══════════════════════════════════════════════════════════════════════════════
# BOM tree / circular reference
# ══════════════════════════════════════════════════════════════════════════════

def test_bom_circular_reference():
    with db.get_conn() as conn:
        _insert_parts(conn, ('A', 'ASSY'), ('B', 'ASSY'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('A','B',1)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('B','A',1)")

    tree = db.build_bom_tree('A')
    assert tree['part_id'] == 'A'
    assert tree['children'][0]['part_id'] == 'B'
    assert tree['children'][0]['children'][0]['error'] == 'Circular reference'


def test_add_bom_row_prevents_cycle():
    """add_bom_row must reject a relationship that would create a cycle."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('A', 'ASSY'), ('B', 'ASSY'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('A','B',1)")

    ok, _ = db.add_bom_row('B', 'A', 1)
    assert not ok


def test_add_bom_row_self_reference_rejected():
    with db.get_conn() as conn:
        _insert_parts(conn, ('A', 'ASSY'))

    ok, _ = db.add_bom_row('A', 'A', 1)
    assert not ok


def test_add_bom_row_requires_assy_or_fab_parent():
    """PRT parts cannot be BOM parents."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('P1', 'PRT'), ('P2', 'PRT'))

    ok, _ = db.add_bom_row('P1', 'P2', 1)
    assert not ok


# ══════════════════════════════════════════════════════════════════════════════
# Flat BOM explode
# ══════════════════════════════════════════════════════════════════════════════

def test_explode_bom_flat():
    with db.get_conn() as conn:
        _insert_parts(conn, ('ASSY1','ASSY'), ('SUB1','ASSY'), ('PART1','PRT'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('ASSY1','SUB1',2)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('SUB1','PART1',3)")

    flat = db.explode_bom_flat('ASSY1')
    assert len(flat) == 2
    part1 = next(r for r in flat if r['part_id'] == 'PART1')
    assert part1['total_qty'] == 6.0


def test_explode_bom_flat_deduped_merges():
    """Parts appearing via two paths must be merged into one row."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('TOP','ASSY'), ('LEFT','ASSY'), ('RIGHT','ASSY'), ('COMMON','PRT'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('TOP','LEFT',1)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('TOP','RIGHT',1)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('LEFT','COMMON',2)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('RIGHT','COMMON',3)")

    result = db.explode_bom_flat_deduped('TOP')
    commons = [r for r in result if r['part_id'] == 'COMMON']
    assert len(commons) == 1
    assert commons[0]['total_qty'] == 5.0  # 2 + 3


def test_explode_bom_flat_optional_zero_qty():
    """Optional components (qty=0) must have total_qty=0 and optional=True."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('ASSY1','ASSY'), ('OPT1','PRT'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('ASSY1','OPT1',0)")

    flat = db.explode_bom_flat('ASSY1')
    assert len(flat) == 1
    assert flat[0]['optional'] is True
    assert flat[0]['total_qty'] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Cost rollup
# ══════════════════════════════════════════════════════════════════════════════

def test_run_rollup():
    with db.get_conn() as conn:
        _insert_parts(conn, ('ASSY1','ASSY',0,1.0), ('SUB1','ASSY',0,2.0), ('PART1','PRT',10.0,0))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('ASSY1','SUB1',2)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('SUB1','PART1',3)")

    db.rollup_all()

    with db.get_conn() as conn:
        assy = conn.execute(
            "SELECT unit_cost, rolled_labor_hrs FROM parts WHERE part_id='ASSY1'"
        ).fetchone()

    assert assy['unit_cost'] == 60.0
    assert assy['rolled_labor_hrs'] == 5.0  # 2*(2.0 + 0) + 1.0


def test_rollup_shared_subassembly_memo():
    """A sub-assembly used by two top-level assemblies should still roll up correctly."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('TOP1','ASSY'), ('TOP2','ASSY'), ('SUB','ASSY'), ('PRT','PRT',10.0))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('SUB','PRT',2)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('TOP1','SUB',1)")
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('TOP2','SUB',3)")

    db.rollup_all()

    with db.get_conn() as conn:
        t1 = conn.execute("SELECT unit_cost FROM parts WHERE part_id='TOP1'").fetchone()
        t2 = conn.execute("SELECT unit_cost FROM parts WHERE part_id='TOP2'").fetchone()

    assert t1['unit_cost'] == 20.0   # 1 * (2*10)
    assert t2['unit_cost'] == 60.0   # 3 * (2*10)


# ══════════════════════════════════════════════════════════════════════════════
# Parts CRUD
# ══════════════════════════════════════════════════════════════════════════════

def test_upsert_part_create():
    data = {
        'type': 'PRT', 'category': 'DLT', 'base_desc': 'RESISTOR',
        'size_spec': '10K', 'variant': '', 'plain_desc': '10K Ohm Resistor',
        'pkg_size': '1', 'pkg_cost': '0.10', 'unit_cost': '0', 'labor_hrs': '0',
        'qty_on_hand': '100', 'status': 'ACTIVE',
    }
    ok, part_id = db.upsert_part(data)
    assert ok
    part = db.get_part(part_id)
    assert part is not None
    assert part['plain_desc'] == '10K Ohm Resistor'
    assert part['unit_cost'] == pytest.approx(0.10)


def test_upsert_part_update():
    data = {
        'type': 'PRT', 'category': 'DLT', 'base_desc': 'WIDGET',
        'pkg_size': '1', 'pkg_cost': '5.00', 'unit_cost': '0', 'labor_hrs': '0',
        'qty_on_hand': '0', 'status': 'ACTIVE',
    }
    _, part_id = db.upsert_part(data)
    data['plain_desc'] = 'Updated Widget'
    ok, result = db.upsert_part(data, orig_part_id=part_id)
    assert ok
    part = db.get_part(result)
    assert part['plain_desc'] == 'Updated Widget'


def test_delete_part_allowed_when_child_in_bom():
    with db.get_conn() as conn:
        _insert_parts(conn, ('ASSY','ASSY'), ('CHILD','PRT'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('ASSY','CHILD',1)")

    ok, _ = db.delete_part('CHILD')
    assert ok


def test_delete_part_allowed_when_has_bom_children():
    with db.get_conn() as conn:
        _insert_parts(conn, ('ASSY','ASSY'), ('CHILD','PRT'))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('ASSY','CHILD',1)")

    ok, _ = db.delete_part('ASSY')
    assert ok


def test_update_part_field_pkg_cost_recalcs_unit_cost():
    """Updating pkg_cost on a PRT should auto-recalculate unit_cost."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('P1', 'PRT', 0))
        conn.execute("UPDATE parts SET pkg_size=10 WHERE part_id='P1'")

    ok, _ = db.update_part_field('P1', 'pkg_cost', '5.0')
    assert ok
    part = db.get_part('P1')
    assert part['unit_cost'] == pytest.approx(0.5)  # 5.0 / 10


def test_update_part_field_rejects_unsafe_field():
    ok, _ = db.update_part_field('X', 'type', 'ASSY')
    assert not ok


# ══════════════════════════════════════════════════════════════════════════════
# Audit trail
# ══════════════════════════════════════════════════════════════════════════════

def _get_log(entity_type=None, entity_id=None, action=None):
    rows = db.get_change_log(entity_type=entity_type, entity_id=entity_id, limit=100)
    if action:
        rows = [r for r in rows if r['action'] == action]
    return rows


def test_audit_log_on_part_create():
    data = {
        'type': 'PRT', 'category': 'DLT', 'base_desc': 'AUDITTEST',
        'pkg_size': '1', 'pkg_cost': '1.00', 'unit_cost': '0', 'labor_hrs': '0',
        'qty_on_hand': '0', 'status': 'ACTIVE',
    }
    ok, part_id = db.upsert_part(data)
    assert ok
    rows = _get_log(entity_type='part', entity_id=part_id, action='create')
    assert len(rows) == 1
    assert rows[0]['user'] == 'test-user'


def test_audit_log_on_part_field_change():
    data = {
        'type': 'PRT', 'category': 'DLT', 'base_desc': 'LOGTEST',
        'pkg_size': '1', 'pkg_cost': '1.00', 'unit_cost': '0', 'labor_hrs': '0',
        'qty_on_hand': '0', 'status': 'ACTIVE',
        'plain_desc': 'Original',
    }
    _, part_id = db.upsert_part(data)
    data['plain_desc'] = 'Changed'
    db.upsert_part(data, orig_part_id=part_id)

    rows = _get_log(entity_type='part', entity_id=part_id, action='update')
    desc_rows = [r for r in rows if r['field'] == 'plain_desc']
    assert len(desc_rows) == 1
    assert desc_rows[0]['old_val'] == 'Original'
    assert desc_rows[0]['new_val'] == 'Changed'


def test_audit_log_on_inline_edit():
    """update_part_field must write a change_log entry."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('P1', 'PRT', 5.0))

    db.update_part_field('P1', 'plain_desc', 'New Desc')

    rows = _get_log(entity_type='part', entity_id='P1', action='update')
    assert any(r['field'] == 'plain_desc' and r['new_val'] == 'New Desc' for r in rows)


def test_audit_log_on_bom_add_and_delete():
    with db.get_conn() as conn:
        _insert_parts(conn, ('A','ASSY'), ('B','PRT'))

    db.add_bom_row('A', 'B', 2)
    rows = _get_log(entity_type='bom', entity_id='A', action='create')
    assert len(rows) == 1

    db.delete_bom_row('A', 'B')
    rows = _get_log(entity_type='bom', entity_id='A', action='delete')
    assert len(rows) == 1


def test_audit_log_on_project_create_and_delete():
    db.upsert_project({'project_id': 'PROJ-LOG', 'status': 'ACTIVE'})
    rows = _get_log(entity_type='project', entity_id='PROJ-LOG', action='create')
    assert len(rows) == 1

    db.delete_project('PROJ-LOG')
    rows = _get_log(entity_type='project', entity_id='PROJ-LOG', action='delete')
    assert len(rows) == 1


def test_diff_log_no_spurious_entries_for_zero_fields():
    """Saving a quote with all-zero numeric fields against a fresh (NULL) DB row
    must NOT produce spurious audit entries for zero values.
    None vs 0, and string '0' vs integer 0, must all compare equal."""
    db.upsert_project({'project_id': 'NOISE-TEST'})

    # Mirrors what the real quote form always submits — all fields present
    quote_data = {
        'overhead_rate': 1.0,   # default, not a "change" vs NULL
        'markup_pct': 0,
        'freight_inbound': 0,
        'freight_outbound': 0,
        'cal_gases_cost': 0,
        'cal_gases_freight': 0,
        'training_days': 0,
        'training_cost': '0',   # string '0' from a form POST
        'discount_pct': 0.0,
        'discount_flat': 0,
        'other_items': [],
    }

    # First save — old row is all NULL; zero fields must NOT be logged
    db.save_quote('NOISE-TEST', dict(quote_data))
    rows = _get_log(entity_type='quote', entity_id='NOISE-TEST', action='update')
    zero_noise = [r for r in rows if r['new_val'] in ('0', '0.0', None, '')]
    assert zero_noise == [], f"Spurious zero-value log entries: {zero_noise}"

    # Second save with identical data — must produce zero new entries
    before_count = len(_get_log(entity_type='quote', entity_id='NOISE-TEST'))
    db.save_quote('NOISE-TEST', dict(quote_data))
    after_count = len(_get_log(entity_type='quote', entity_id='NOISE-TEST'))
    assert after_count == before_count, (
        f"Repeated identical save created {after_count - before_count} new log entries"
    )




def test_diff_log_does_log_real_changes():
    """Real changes from 0 → non-zero and non-zero → different must still be logged."""
    db.upsert_project({'project_id': 'REAL-CHANGE'})
    db.save_quote('REAL-CHANGE', {'markup_pct': 0, 'other_items': []})

    db.save_quote('REAL-CHANGE', {'markup_pct': 25, 'other_items': []})
    rows = _get_log(entity_type='quote', entity_id='REAL-CHANGE', action='update')
    markup_rows = [r for r in rows if r['field'] == 'markup_pct']
    assert len(markup_rows) == 1
    assert markup_rows[0]['new_val'] == '25'

    db.save_quote('REAL-CHANGE', {'markup_pct': 10, 'other_items': []})
    rows = _get_log(entity_type='quote', entity_id='REAL-CHANGE', action='update')
    markup_rows = [r for r in rows if r['field'] == 'markup_pct']
    assert len(markup_rows) == 2



# ══════════════════════════════════════════════════════════════════════════════
# Project lifecycle
# ══════════════════════════════════════════════════════════════════════════════

def test_project_create_and_get():
    ok, pid = db.upsert_project({
        'project_id': 'TEST-001', 'status': 'ACTIVE',
        'customer': 'Acme', 'labor_rate': '30', 'markup': '15',
    })
    assert ok
    p = db.get_project('TEST-001')
    assert p['customer'] == 'Acme'
    assert p['labor_rate'] == 30.0
    assert p['markup'] == 15.0


def test_project_item_lifecycle():
    db.upsert_project({'project_id': 'P1'})
    with db.get_conn() as conn:
        _insert_parts(conn, ('PRT-A', 'PRT', 10.0))

    ok, _ = db.add_project_item('P1', 'PRT-A', 2)
    assert ok

    items = db.get_project_items('P1')
    assert len(items) == 1
    item_id = items[0]['id']

    db.update_project_item(item_id, qty=5)
    assert db.get_project_items('P1')[0]['qty'] == 5.0

    db.set_project_item_type(item_id, 'STANDARD')
    assert db.get_project_items('P1')[0]['item_type'] == 'STANDARD'

    ok, _ = db.delete_project_item(item_id)
    assert ok
    assert db.get_project_items('P1') == []


def test_project_clone_carries_items_and_quote():
    db.upsert_project({'project_id': 'SRC', 'labor_rate': '40', 'markup': '20'})
    with db.get_conn() as conn:
        _insert_parts(conn, ('PART-X', 'PRT', 50.0))
    db.add_project_item('SRC', 'PART-X', 3)
    db.save_quote('SRC', {
        'overhead_rate': 1.2, 'markup_pct': 20,
        'freight_inbound': 100, 'other_items': [],
    })

    ok, new_id = db.clone_project('SRC', 'CLONE-01')
    assert ok

    items = db.get_project_items('CLONE-01')
    assert len(items) == 1
    assert items[0]['part_id'] == 'PART-X'
    assert items[0]['qty'] == 3.0

    q = db.get_or_create_quote('CLONE-01')
    assert q['overhead_rate'] == pytest.approx(1.2)
    assert q['freight_inbound'] == pytest.approx(100.0)


# ══════════════════════════════════════════════════════════════════════════════
# Quotes
# ══════════════════════════════════════════════════════════════════════════════

def test_save_quote_and_retrieve():
    db.upsert_project({'project_id': 'Q-TEST'})
    ok, _ = db.save_quote('Q-TEST', {
        'overhead_rate': 1.15, 'markup_pct': 25, 'discount_pct': 5,
        'internal_notes': 'Test note', 'other_items': [],
    })
    assert ok

    q = db.get_or_create_quote('Q-TEST')
    assert q['overhead_rate'] == pytest.approx(1.15)
    assert q['markup_pct'] == pytest.approx(25.0)
    assert q['discount_pct'] == pytest.approx(5.0)
    assert q['internal_notes'] == 'Test note'


def test_quote_optimistic_locking_rejects_stale_save():
    db.upsert_project({'project_id': 'OL-TEST'})
    db.save_quote('OL-TEST', {'other_items': [], 'overhead_rate': 1.0})

    q = db.get_or_create_quote('OL-TEST')
    real_ts = q['updated_at']

    # Second save with a stale timestamp must be rejected
    ok, msg = db.save_quote('OL-TEST', {
        'other_items': [], 'overhead_rate': 1.5,
        'updated_at': '2000-01-01T00:00:00',
    })
    assert not ok
    assert 'refresh' in msg.lower()

    # A save with the correct timestamp must succeed
    ok, _ = db.save_quote('OL-TEST', {
        'other_items': [], 'overhead_rate': 1.5,
        'updated_at': real_ts,
    })
    assert ok


def test_quote_freeze_and_unfreeze():
    db.upsert_project({'project_id': 'FRZ'})
    with db.get_conn() as conn:
        _insert_parts(conn, ('ASY1', 'ASSY', 200.0))
    db.add_project_item('FRZ', 'ASY1', 1)

    # Freeze: save a frozen snapshot manually
    db.save_quote('FRZ', {
        'costs_frozen': 1,
        'frozen_material': 200.0, 'frozen_labor_hrs': 5.0,
        'other_items': [],
    })
    q = db.get_or_create_quote('FRZ')
    assert q['costs_frozen'] == 1
    assert q['frozen_material'] == pytest.approx(200.0)

    # Unfreeze
    db.save_quote('FRZ', {**q, 'costs_frozen': 0, 'other_items': []})
    q2 = db.get_or_create_quote('FRZ')
    assert q2['costs_frozen'] == 0


# ══════════════════════════════════════════════════════════════════════════════
# System flags
# ══════════════════════════════════════════════════════════════════════════════

def test_system_flags_zero_cost():
    with db.get_conn() as conn:
        _insert_parts(conn, ('P-ZEROCOST', 'PRT', 0))

    flags = db.get_system_flags()
    ids = [f['part_id'] for f in flags['zero_cost']]
    assert 'P-ZEROCOST' in ids


def test_system_flags_empty_bom():
    with db.get_conn() as conn:
        _insert_parts(conn, ('EMPTY-ASSY', 'ASSY'))

    flags = db.get_system_flags()
    ids = [f['part_id'] for f in flags['empty_bom']]
    assert 'EMPTY-ASSY' in ids


def test_system_flags_orphaned_part():
    with db.get_conn() as conn:
        _insert_parts(conn, ('ORPHAN-PRT', 'PRT', 5.0))

    flags = db.get_system_flags()
    ids = [f['part_id'] for f in flags['orphaned']]
    assert 'ORPHAN-PRT' in ids


def test_system_flags_clean_when_no_issues():
    """An ASSY with children and no zero-cost PRTs should have empty flag lists."""
    with db.get_conn() as conn:
        _insert_parts(conn, ('A1','ASSY'), ('P1','PRT',1.0))
        conn.execute("INSERT INTO bom (parent_id, child_id, qty) VALUES ('A1','P1',1)")

    flags = db.get_system_flags()
    assert 'A1' not in [f['part_id'] for f in flags['empty_bom']]
    assert 'P1' not in [f['part_id'] for f in flags['zero_cost']]
    assert 'P1' not in [f['part_id'] for f in flags['orphaned']]
