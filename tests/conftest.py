import sys
from pathlib import Path

# make the repo root importable (db, enricher, utils packages)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeCursor:
    """Records statements without touching a database."""

    def __init__(self, connection, rows=None):
        self.connection = connection
        self.executed = []
        self.executed_params = []
        self.copied_rows = []
        # rows returned by fetchone, in order
        self.rows = list(rows or [])

    def execute(self, statement, params=None):
        self.executed.append(statement)
        self.executed_params.append(params)

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def copy_expert(self, sql, file):
        self.executed.append(sql)
        self.copied_rows += file.read().splitlines()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    """Records commits and closes without touching a database."""

    def __init__(self, rows=None):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.cursors = []
        self.rows = rows

    def cursor(self):
        cursor = FakeCursor(self, self.rows)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True
