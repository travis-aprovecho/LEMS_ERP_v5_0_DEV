"""
utils.py — LEMS ERP utility functions

Backup strategy
---------------
Two triggers:
  1. On server startup — always backs up before any changes are made.
  2. On first write after an idle period — backs up at natural session
     breakpoints rather than on every single save.

Configuration
-------------
IDLE_BACKUP_MINUTES : int
    How many minutes of inactivity before the next write triggers a backup.
    Default is 30. Change this value to suit your workflow.
    NOTE: Update README.md if this value is changed.

KEEP_BACKUPS : int
    Number of recent backups to keep in /backups/. Older files are moved
    to /backups/archive/. Default is 10.
"""

import os
import shutil
import sqlite3
import threading
import datetime
import logging

# ── Configuration ──────────────────────────────────────────────────────────────
IDLE_BACKUP_MINUTES = 30
KEEP_BACKUPS        = 10

# ── Internal state ─────────────────────────────────────────────────────────────
_last_backup_time: datetime.datetime | None = None
_backup_lock = threading.Lock()


def backup_db(db_path: str, reason: str = 'manual') -> str | None:
    """
    Create a timestamped hot-copy of the SQLite database.

    Uses sqlite3's backup() API which is safe to call even if writes
    are in progress — no corruption risk.

    Returns the path of the new backup file, or None on failure.
    """
    global _last_backup_time

    db_dir      = os.path.dirname(os.path.abspath(db_path))
    backups_dir = os.path.join(db_dir, 'backups')
    archive_dir = os.path.join(backups_dir, 'archive')

    os.makedirs(backups_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    ts       = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'lems_backup_{ts}_{reason}.db'
    dest     = os.path.join(backups_dir, filename)

    try:
        src_conn  = sqlite3.connect(db_path)
        dest_conn = sqlite3.connect(dest)
        with dest_conn:
            src_conn.backup(dest_conn)
        src_conn.close()
        dest_conn.close()

        _last_backup_time = datetime.datetime.now()
        logging.info("DB backup created: %s", filename)

        _rotate_backups(backups_dir, archive_dir)
        return dest

    except Exception as e:
        logging.warning("DB backup failed (%s): %s", reason, e)
        return None


def _rotate_backups(backups_dir: str, archive_dir: str) -> None:
    """
    Keep the KEEP_BACKUPS most recent .db files in backups_dir.
    Move older ones to archive_dir.
    """
    files = sorted(
        [f for f in os.listdir(backups_dir) if f.endswith('.db')],
        reverse=True   # newest first (timestamps in name sort correctly)
    )
    for old in files[KEEP_BACKUPS:]:
        src  = os.path.join(backups_dir, old)
        dest = os.path.join(archive_dir, old)
        try:
            shutil.move(src, dest)
            logging.info("Archived old backup: %s", old)
        except Exception as e:
            logging.warning("Could not archive %s: %s", old, e)


def should_backup_on_write(db_path: str) -> bool:
    """
    Returns True if enough idle time has passed since the last backup
    to warrant a new one on the next write.
    """
    if _last_backup_time is None:
        return True
    elapsed = (datetime.datetime.now() - _last_backup_time).total_seconds()
    return elapsed >= IDLE_BACKUP_MINUTES * 60


def backup_on_write_if_due(db_path: str) -> None:
    """
    Thread-safe: triggers a backup if the idle period has elapsed.
    Called after any logged write. Does nothing if a backup was recently made.
    """
    with _backup_lock:
        if should_backup_on_write(db_path):
            backup_db(db_path, reason='write')
