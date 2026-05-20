import sqlite3
import database as db

db.DB_PATH = 'test_core.db'
if __name__ == '__main__':
    db.init_db()
    
    # 1. Upsert
    db.upsert_part({
        'part_id': 'TEST-PRT-1',
        'type': 'PRT',
        'category': 'STD',
        'unit_cost': '1.50'
    })
    
    with db.get_conn() as conn:
        print("After insert:", conn.execute("SELECT unit_cost FROM parts WHERE part_id='TEST-PRT-1'").fetchone()[0])
        
    # 2. Update
    ok, msg = db.update_part_field('TEST-PRT-1', 'unit_cost', '2.00')
    print("Update result:", ok, msg)
    
    with db.get_conn() as conn:
        print("After update:", conn.execute("SELECT unit_cost FROM parts WHERE part_id='TEST-PRT-1'").fetchone()[0])
        
    # 3. Check history
    print("History:", db.get_part_cost_history('TEST-PRT-1'))
