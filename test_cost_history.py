import os
import sqlite3
import pytest

import database as db

# The test overrides db.DB_PATH dynamically in setup
db.DB_PATH = "test_core.db"

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    if os.path.exists("test_core.db"):
        os.remove("test_core.db")
    db.init_db()
    yield
    # Teardown
    if os.path.exists("test_core.db"):
        os.remove("test_core.db")

def test_cost_history_logging():
    # Insert a new part with initial cost 1.50
    ok, part_id = db.upsert_part({
        'type': 'PRT',
        'category': 'STD',
        'base_desc': 'TEST PART',
        'unit_cost': '1.50'
    })
    assert ok
    
    # Update cost to 2.00
    db.update_part_field(part_id, 'unit_cost', '2.00')
    
    # Check history
    history = db.get_part_cost_history(part_id)
    assert len(history) == 1
    assert history[0]['old_cost'] == 1.50
    assert history[0]['new_cost'] == 2.00
    
    # Update cost back to 1.50 using upsert
    db.upsert_part({
        'type': 'PRT',
        'category': 'STD',
        'base_desc': 'TEST PART',
        'unit_cost': '1.50'
    }, orig_part_id=part_id)
    
    history = db.get_part_cost_history(part_id)
    assert len(history) == 2
    assert history[0]['old_cost'] == 2.00
    assert history[0]['new_cost'] == 1.50
