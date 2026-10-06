"""Run: DATABASE_URL="postgresql://user:pass@host:5432/db" python test_postgres.py

Skips with a message when DATABASE_URL is unset, so it is safe to run anywhere.
Anything that speaks Postgres works: a container from compose.yaml, or a hosted
database. The code cannot tell the difference, which is the point.

It writes to a table called `tasks` and cleans up the rows it adds.
"""
import os
import sys

if not os.environ.get("DATABASE_URL"):
    print("skipped: set DATABASE_URL to run this against a real Postgres")
    sys.exit(0)

import db_postgres as db

# Tests run in alphabetical order, so test_an_id... comes before the seed test.
# Create the table first, as main.py does at startup, or a fresh database fails.
db.init()


def test_seed_runs_once():
    db.init()
    before = len(db.all_tasks())
    db.init()
    db.init()
    assert len(db.all_tasks()) == before, "seeding must only fill an empty table"


def test_full_crud():
    created = db.insert("test row, safe to delete")
    try:
        assert created["done"] is False
        assert db.one_task(created["id"])["title"] == "test row, safe to delete"

        updated = db.update(created["id"], done=True)
        assert updated["done"] is True
        # Postgres has a real boolean, unlike SQLite's 0/1 -- check it survives.
        assert isinstance(updated["done"], bool)

        renamed = db.update(created["id"], title="renamed")
        assert renamed["title"] == "renamed" and renamed["done"] is True
    finally:
        db.delete(created["id"])
    assert db.one_task(created["id"]) is None


def test_unknown_id_is_none_not_an_error():
    assert db.one_task(999_999) is None


def test_ids_are_not_reused():
    a = db.insert("first")
    b = db.insert("second")
    db.delete(b["id"])
    c = db.insert("third")
    try:
        assert c["id"] != b["id"], "SERIAL must never hand out a deleted id again"
    finally:
        db.delete(a["id"])
        db.delete(c["id"])


def test_an_id_that_looks_like_sql_is_treated_as_a_value():
    before = len(db.all_tasks())
    try:
        db.one_task("1; DROP TABLE tasks")
    except Exception:
        pass          # the driver refusing it is the correct outcome
    assert len(db.all_tasks()) == before, "the table should still exist"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
    print("all checks passed")
