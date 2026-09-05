"""Tests for the /api/history router."""

import pytest
from fastapi import HTTPException

from app.market.cache import PriceCache
from app.market.history import _build_history_response, create_history_router


class TestBuildHistoryResponse:
    """Unit tests for the response-building helper (no HTTP layer needed)."""

    def test_unknown_ticker_raises_404(self):
        cache = PriceCache()
        with pytest.raises(HTTPException) as exc_info:
            _build_history_response("NOPE", 300, cache, lambda: ["AAPL"])
        assert exc_info.value.status_code == 404

    def test_tracked_but_not_warmed_returns_empty_points(self):
        """A tracked ticker with no cached price yet returns 200 with []."""
        cache = PriceCache()
        result = _build_history_response("AAPL", 300, cache, lambda: ["AAPL"])
        assert result == {"ticker": "AAPL", "points": []}

    def test_returns_points_for_tracked_ticker(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00, timestamp=1.0)
        cache.update("AAPL", 191.00, timestamp=2.0)

        result = _build_history_response("AAPL", 300, cache, lambda: ["AAPL"])
        assert result["ticker"] == "AAPL"
        assert [p["price"] for p in result["points"]] == [190.00, 191.00]

    def test_ticker_is_normalized(self):
        """Lowercase/whitespace input is normalized before lookup."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)

        result = _build_history_response(" aapl ", 300, cache, lambda: ["AAPL"])
        assert result["ticker"] == "AAPL"

    def test_limit_is_applied(self):
        cache = PriceCache()
        for i in range(5):
            cache.update("AAPL", 190.00 + i, timestamp=float(i))

        result = _build_history_response("AAPL", 2, cache, lambda: ["AAPL"])
        assert [p["timestamp"] for p in result["points"]] == [3.0, 4.0]


class TestCreateHistoryRouter:
    """Sanity checks on the router factory wiring."""

    def test_router_exposes_history_path(self):
        cache = PriceCache()
        router = create_history_router(cache, lambda: ["AAPL"])
        paths = [route.path for route in router.routes]
        assert "/api/history" in paths
