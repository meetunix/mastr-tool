import sys
from pathlib import Path

# make the repo root importable (db, enricher, utils packages)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeCursor:
    """Records statements without touching a database."""

    def __init__(self, connection):
        self.connection = connection
        self.mogrify_calls = 0
        self.executed = []

    def mogrify(self, statement, params):
        self.mogrify_calls += 1
        return b"statement"

    def execute(self, statement, params=None):
        self.executed.append(statement)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    """Records commits and closes without touching a database."""

    def __init__(self):
        self.commits = 0
        self.closed = False
        self.cursors = []

    def cursor(self):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True
