"""Append-only through the application API; SQLite is not a tamper-proof ledger."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: str):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                parent_id TEXT REFERENCES runs(id),
                payload TEXT NOT NULL
            )""")
            with connection:
                yield connection
        finally:
            connection.close()

    def put(self, record: dict):
        with self.connect() as connection:
            connection.execute("INSERT INTO runs VALUES (?, ?, ?)", (
                record["id"], record["parent_id"], json.dumps(record, ensure_ascii=False)))

    def get(self, run_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def ready(self):
        with self.connect() as connection:
            connection.execute("SELECT 1").fetchone()
