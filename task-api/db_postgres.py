"""The same storage interface as db.py, backed by PostgreSQL instead of SQLite.

This is the third storage engine behind identical routes: a Python list, then a
file, now a database server in a container. main.py imports whichever module
matches the environment and calls the same seven functions. Nothing in the API
layer knows the difference -- that is the whole point of keeping SQL in one file.

Two differences from the SQLite version worth knowing:
  - placeholders are %s, not ?
  - Postgres has a real boolean, so no 0/1 translation is needed
"""
import os
from contextlib import closing

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "")

SEED = [
    ("Read the assignment brief", True),
    ("Build the task API", False),
    ("Publish it to GitHub", False),
]


def connect():
    # closing() guarantees the socket is released; the `with con` inside each
    # function is what commits or rolls back.
    return closing(psycopg.connect(DATABASE_URL, row_factory=dict_row))


def ping():
    """Ask the database one trivial question. Raises if it cannot answer."""
    with connect() as con:
        con.execute("SELECT 1")


def init():
    with connect() as con, con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "  id SERIAL PRIMARY KEY,"
            "  title TEXT NOT NULL,"
            "  done BOOLEAN NOT NULL DEFAULT FALSE)"
        )
        empty = con.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0
        if empty:
            con.cursor().executemany(
                "INSERT INTO tasks (title, done) VALUES (%s, %s)", SEED)


def as_task(row):
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def all_tasks():
    with connect() as con, con:
        return [as_task(r) for r in con.execute("SELECT * FROM tasks ORDER BY id")]


def one_task(task_id):
    with connect() as con, con:
        # Parameterized, always. Gluing the id into the string is how SQL
        # injection happens: an id of "1; DROP TABLE tasks" would be run as SQL.
        # Passed as a parameter it is only ever a value, never code.
        row = con.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
    return as_task(row) if row else None


def insert(title):
    with connect() as con, con:
        row = con.execute(
            "INSERT INTO tasks (title, done) VALUES (%s, FALSE) RETURNING *", (title,)
        ).fetchone()
    return as_task(row)


def update(task_id, title=None, done=None):
    sets, values = [], []
    if title is not None:
        sets.append("title = %s")
        values.append(title)
    if done is not None:
        sets.append("done = %s")
        values.append(done)
    values.append(task_id)
    with connect() as con, con:
        row = con.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s RETURNING *", values
        ).fetchone()
    return as_task(row) if row else None


def delete(task_id):
    with connect() as con, con:
        con.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
