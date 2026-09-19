"""Fixtures: a real app instance over a temp DB and a deterministic stub market source."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market import PriceCache
from tests.portfolio.stubs import StubSource


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "finally.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "no-static"))
    cache = PriceCache()
    return SimpleNamespace(cache=cache, source=StubSource(cache), tmp_path=tmp_path)


@pytest.fixture
def client(api_env):
    app = create_app(cache=api_env.cache, source=api_env.source, start_background_tasks=False)
    with TestClient(app) as test_client:
        test_client.env = api_env
        yield test_client
