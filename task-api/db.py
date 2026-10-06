"""Everything that touches SQLite lives here.

main.py never writes SQL. That line is deliberate: the next assignment swaps
SQLite for PostgreSQL, and if it goes well only this file changes.
"""
import os
import sqlite3
from contextlib import closing, contextmanager

DB_PATH = os.environ.get("TASKS_DB", "tasks.db")

SEED = [
    ("Read the assignment brief", 1),
    ("Build the task API", 0),
    ("Publish it to GitHub", 0),
]


@contextmanager
def connect():
    """Open, commit-or-rollback, and -- the part sqlite3 does not do for you -- close.

    `with sqlite3.connect(...)` only manages the transaction. The connection
    stays open, and on Windows an open connection means the .db file cannot be
    deleted or moved. Wrapping it in closing() is the whole fix.
    """
    con = sqlite3.connect(DB_PATH)
    # Rows arrive as tuples by default. This makes them behave like dicts, so
    # row["title"] works and the API layer never counts column positions.
    con.row_factory = sqlite3.Row
    with closing(con), con:
        yield con


def ping():
    """Ask the database one trivial question. Raises if it cannot answer."""
    with connect() as con:
        con.execute("SELECT 1")


def init():
    """Create the file and table if missing, and seed only an empty table."""
    with connect() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  title TEXT NOT NULL,"
            "  done INTEGER NOT NULL DEFAULT 0)"
        )
        empty = con.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0
        if empty:
            con.executemany("INSERT INTO tasks (title, done) VALUES (?, ?)", SEED)


def as_task(row):
    """SQLite has no boolean type -- done is stored as 0/1, so translate on the way out."""
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def all_tasks():
    with connect() as con:
        return [as_task(r) for r in con.execute("SELECT * FROM tasks ORDER BY id")]


def one_task(task_id):
    with connect() as con:
        row = con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return as_task(row) if row else None


def insert(title):
    with connect() as con:
        cur = con.execute("INSERT INTO tasks (title, done) VALUES (?, 0)", (title,))
        return {"id": cur.lastrowid, "title": title, "done": False}


def update(task_id, title=None, done=None):
    sets, values = [], []
    if title is not None:
        sets.append("title = ?")
        values.append(title)
    if done is not None:
        sets.append("done = ?")
        values.append(int(done))
    values.append(task_id)
    with connect() as con:
        con.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
    return one_task(task_id)


def delete(task_id):
    with connect() as con:
        con.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
