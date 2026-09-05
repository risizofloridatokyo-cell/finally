"""Tests for PriceCache."""

from app.market.cache import HISTORY_MAXLEN, PriceCache


class TestPriceCache:
    """Unit tests for the PriceCache."""

    def test_update_and_get(self):
        """Test updating and getting a price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert cache.get("AAPL") == update

    def test_first_update_is_flat(self):
        """Test that the first update has flat direction."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.direction == "flat"
        assert update.previous_price == 190.50

    def test_direction_up(self):
        """Test price update with upward direction."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 191.00)
        assert update.direction == "up"
        assert update.change == 1.00

    def test_direction_down(self):
        """Test price update with downward direction."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 189.00)
        assert update.direction == "down"
        assert update.change == -1.00

    def test_remove(self):
        """Test removing a ticker from cache."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.remove("AAPL")
        assert cache.get("AAPL") is None

    def test_remove_nonexistent(self):
        """Test removing a ticker that doesn't exist."""
        cache = PriceCache()
        cache.remove("AAPL")  # Should not raise

    def test_get_all(self):
        """Test getting all prices."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        all_prices = cache.get_all()
        assert set(all_prices.keys()) == {"AAPL", "GOOGL"}

    def test_version_increments(self):
        """Test that version counter increments."""
        cache = PriceCache()
        v0 = cache.version
        cache.update("AAPL", 190.00)
        assert cache.version == v0 + 1
        cache.update("AAPL", 191.00)
        assert cache.version == v0 + 2

    def test_get_price_convenience(self):
        """Test the convenience get_price method."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("NOPE") is None

    def test_len(self):
        """Test __len__ method."""
        cache = PriceCache()
        assert len(cache) == 0
        cache.update("AAPL", 190.00)
        assert len(cache) == 1
        cache.update("GOOGL", 175.00)
        assert len(cache) == 2

    def test_contains(self):
        """Test __contains__ method."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        assert "AAPL" in cache
        assert "GOOGL" not in cache

    def test_custom_timestamp(self):
        """Test updating with a custom timestamp."""
        cache = PriceCache()
        custom_ts = 1234567890.0
        update = cache.update("AAPL", 190.50, timestamp=custom_ts)
        assert update.timestamp == custom_ts

    def test_price_rounding(self):
        """Test that prices are rounded to 2 decimal places."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.12345)
        assert update.price == 190.12

    def test_get_history_unknown_ticker(self):
        """Test that history for an untracked ticker is an empty list."""
        cache = PriceCache()
        assert cache.get_history("NOPE") == []

    def test_get_history_oldest_first(self):
        """Test that history points are returned oldest-first."""
        cache = PriceCache()
        cache.update("AAPL", 190.00, timestamp=1.0)
        cache.update("AAPL", 191.00, timestamp=2.0)
        cache.update("AAPL", 192.00, timestamp=3.0)

        history = cache.get_history("AAPL")
        assert [p["timestamp"] for p in history] == [1.0, 2.0, 3.0]
        assert [p["price"] for p in history] == [190.00, 191.00, 192.00]

    def test_get_history_limit(self):
        """Test that limit caps the number of most-recent points returned."""
        cache = PriceCache()
        for i in range(5):
            cache.update("AAPL", 190.00 + i, timestamp=float(i))

        history = cache.get_history("AAPL", limit=2)
        assert [p["timestamp"] for p in history] == [3.0, 4.0]

    def test_get_history_limit_larger_than_available(self):
        """Test that a limit larger than the buffer just returns everything."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        history = cache.get_history("AAPL", limit=300)
        assert len(history) == 1

    def test_get_history_bounded_ring_buffer(self):
        """Test that the history buffer evicts the oldest points past capacity."""
        cache = PriceCache()
        for i in range(HISTORY_MAXLEN + 10):
            cache.update("AAPL", 100.0 + i, timestamp=float(i))

        history = cache.get_history("AAPL")
        assert len(history) == HISTORY_MAXLEN
        # Oldest 10 points should have been evicted.
        assert history[0]["timestamp"] == 10.0
        assert history[-1]["timestamp"] == float(HISTORY_MAXLEN + 9)

    def test_get_history_isolated_per_ticker(self):
        """Test that history buffers don't leak across tickers."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)

        assert len(cache.get_history("AAPL")) == 1
        assert len(cache.get_history("GOOGL")) == 1

    def test_remove_clears_history(self):
        """Test that removing a ticker also clears its history buffer."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.remove("AAPL")
        assert cache.get_history("AAPL") == []
