"""Fixtures for DB-layer tests: every test gets its own temp SQLite file."""

import pytest

from app.db import connection


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "finally.db"
    monkeypatch.setenv("DB_PATH", str(path))
    connection._initialized.discard(str(path.resolve()))
    return path
