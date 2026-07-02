import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "data" / "songforge.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("DB:", db)
print("Tables:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")])

rows = c.execute(
    """
    SELECT id, title, task_id, status, created_at, fail_msg, user_id, guest_id
    FROM generations
    ORDER BY created_at DESC
    LIMIT 12
    """
).fetchall()
print("\nLast generations:")
for r in rows:
    d = dict(r)
    d["id"] = (d["id"] or "")[:8] + "..."
    print(d)