"""
Tests for server.py — Stock Analyst MCP tools.

All yfinance calls are mocked; no network access occurs.
The cache is patched out in unit tests so no SQLite DB is needed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure server.py (and cache.py) are importable from this directory.
sys.path.insert(0, str(Path(__file__).parent))

import server as srv


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _fast_info(
    last_price: float = 175.5,
    previous_close: float = 170.0,
    last_volume: int = 5_000_000,
    market_cap: int = 2_750_000_000_000,
) -> MagicMock:
    fi = MagicMock()
    fi.last_price = last_price
    fi.previous_close = previous_close
    fi.last_volume = last_volume
    fi.market_cap = market_cap
    return fi


SAMPLE_INFO = {
    "longName": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "longBusinessSummary": "A" * 700,   # intentionally longer than 600 chars
    "trailingPE": 28.5,
    "forwardPE": 25.0,
    "fiftyTwoWeekHigh": 200.0,
    "fiftyTwoWeekLow": 140.0,
    "dividendYield": 0.005,
    "beta": 1.2,
    "trailingEps": 6.13,
}


def _history_df() -> pd.DataFrame:
    """Three-row OHLCV DataFrame mimicking yf.Ticker.history()."""
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.DataFrame(
        {
            "Open":   [185.0, 183.5, 186.0],
            "High":   [187.0, 185.0, 188.0],
            "Low":    [184.0, 182.0, 185.0],
            "Close":  [186.5, 184.0, 187.5],
            "Volume": [60_000_000, 55_000_000, 65_000_000],
        },
        index=index,
    )


def _financials_df() -> pd.DataFrame:
    """
    Income-statement DataFrame mimicking yf.Ticker.financials.
    Rows = line items, Columns = fiscal-year-end Timestamps.
    """
    cols = pd.to_datetime(["2023-09-30", "2022-09-30", "2021-09-30", "2020-09-30"])
    return pd.DataFrame(
        {
            cols[0]: [383_285_000_000,  96_995_000_000, 169_148_000_000],
            cols[1]: [394_328_000_000,  99_803_000_000, 170_782_000_000],
            cols[2]: [365_817_000_000,  94_680_000_000, 152_836_000_000],
            cols[3]: [274_515_000_000,  57_411_000_000, 104_956_000_000],
        },
        index=["Total Revenue", "Net Income", "Gross Profit"],
    )


# Shared fixture: cache always misses, put is a no-op.
@pytest.fixture
def no_cache():
    with patch("server.cache_store.get", return_value=None), \
         patch("server.cache_store.put"):
        yield


# ─── _validate ────────────────────────────────────────────────────────────────


class TestValidate:
    def test_valid_ticker_returned_uppercase(self):
        assert srv._validate("aapl") == "AAPL"

    def test_leading_trailing_whitespace_stripped(self):
        assert srv._validate("  msft  ") == "MSFT"

    def test_invalid_ticker_raises_value_error(self):
        with pytest.raises(ValueError, match="not supported"):
            srv._validate("XYZ")

    @pytest.mark.parametrize("ticker", sorted(srv.ALLOWED_TICKERS))
    def test_all_allowed_tickers_accepted(self, ticker):
        assert srv._validate(ticker) == ticker


# ─── get_current_price ────────────────────────────────────────────────────────


class TestGetCurrentPrice:
    def test_returns_expected_keys(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.fast_info = _fast_info()
            result = srv.get_current_price("AAPL")
        assert set(result) == {"ticker", "price", "change", "change_pct", "volume", "market_cap"}

    def test_computed_values_are_correct(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.fast_info = _fast_info(last_price=175.5, previous_close=170.0)
            result = srv.get_current_price("AAPL")
        assert result["ticker"] == "AAPL"
        assert result["price"] == 175.5
        assert result["change"] == 5.5
        assert result["change_pct"] == round(5.5 / 170.0 * 100, 2)

    def test_zero_previous_close_yields_none_pct(self, no_cache):
        # prev_close = previous_close or last_price; None only when both are falsy.
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.fast_info = _fast_info(last_price=0, previous_close=0)
            result = srv.get_current_price("AAPL")
        assert result["change_pct"] is None

    def test_invalid_ticker_raises(self):
        with pytest.raises(ValueError):
            srv.get_current_price("FAKE")

    def test_cache_hit_skips_yfinance(self):
        cached = {
            "ticker": "AAPL", "price": 100.0, "change": 0.0,
            "change_pct": 0.0, "volume": 1, "market_cap": 1,
        }
        with patch("server.cache_store.get", return_value=cached), \
             patch("server.yf.Ticker") as mock_yf:
            result = srv.get_current_price("AAPL")
        mock_yf.assert_not_called()
        assert result == cached

    def test_cache_miss_stores_result(self):
        with patch("server.cache_store.get", return_value=None), \
             patch("server.cache_store.put") as mock_put, \
             patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.fast_info = _fast_info()
            result = srv.get_current_price("AAPL")
        mock_put.assert_called_once_with("price:AAPL", "price", result)


# ─── get_stock_overview ───────────────────────────────────────────────────────


class TestGetStockOverview:
    def test_returns_expected_keys(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.info = SAMPLE_INFO
            result = srv.get_stock_overview("AAPL")
        assert set(result) == {
            "ticker", "name", "sector", "industry", "description",
            "pe_ratio", "forward_pe", "52w_high", "52w_low", "dividend_yield", "beta",
        }

    def test_description_truncated_to_600_chars(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.info = SAMPLE_INFO
            result = srv.get_stock_overview("AAPL")
        assert len(result["description"]) == 600

    def test_values_mapped_correctly(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.info = SAMPLE_INFO
            result = srv.get_stock_overview("AAPL")
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "Technology"
        assert result["pe_ratio"] == 28.5
        assert result["52w_high"] == 200.0
        assert result["dividend_yield"] == 0.005

    def test_missing_info_keys_become_none(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.info = {}
            result = srv.get_stock_overview("AAPL")
        assert result["name"] is None
        assert result["pe_ratio"] is None
        assert result["description"] == ""

    def test_cache_hit_skips_yfinance(self):
        cached = {"ticker": "AAPL", "name": "Apple Inc."}
        with patch("server.cache_store.get", return_value=cached), \
             patch("server.yf.Ticker") as mock_yf:
            srv.get_stock_overview("AAPL")
        mock_yf.assert_not_called()

    def test_cache_miss_stores_result(self):
        with patch("server.cache_store.get", return_value=None), \
             patch("server.cache_store.put") as mock_put, \
             patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.info = SAMPLE_INFO
            result = srv.get_stock_overview("MSFT")
        mock_put.assert_called_once_with("overview:MSFT", "overview", result)


# ─── get_price_history ───────────────────────────────────────────────────────


class TestGetPriceHistory:
    def test_returns_expected_top_level_keys(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL")
        assert set(result) == {"ticker", "period", "data"}

    def test_each_record_has_correct_keys(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL")
        expected_keys = {"date", "open", "high", "low", "close", "volume"}
        assert all(set(r) == expected_keys for r in result["data"])

    def test_record_count_matches_dataframe_rows(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL")
        assert len(result["data"]) == 3

    def test_default_period_is_1mo(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL")
        mock_yf.return_value.history.assert_called_once_with(period="1mo")
        assert result["period"] == "1mo"

    @pytest.mark.parametrize("period", ["5d", "1mo", "3mo", "1y"])
    def test_valid_periods_are_forwarded(self, no_cache, period):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL", period=period)
        mock_yf.return_value.history.assert_called_once_with(period=period)
        assert result["period"] == period

    def test_unknown_period_falls_back_to_1mo(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL", period="99y")
        mock_yf.return_value.history.assert_called_once_with(period="1mo")
        assert result["period"] == "1mo"

    def test_date_formatted_as_yyyy_mm_dd(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL")
        assert result["data"][0]["date"] == "2024-01-02"

    def test_volume_is_integer(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("AAPL")
        assert isinstance(result["data"][0]["volume"], int)

    def test_cache_hit_skips_yfinance(self):
        cached = {"ticker": "AAPL", "period": "1mo", "data": []}
        with patch("server.cache_store.get", return_value=cached), \
             patch("server.yf.Ticker") as mock_yf:
            srv.get_price_history("AAPL")
        mock_yf.assert_not_called()

    def test_cache_miss_stores_result(self):
        with patch("server.cache_store.get", return_value=None), \
             patch("server.cache_store.put") as mock_put, \
             patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = _history_df()
            result = srv.get_price_history("NVDA", period="5d")
        mock_put.assert_called_once_with("history:NVDA:5d", "history", result)


# ─── get_financials ──────────────────────────────────────────────────────────


class TestGetFinancials:
    def test_returns_expected_top_level_keys(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {"trailingEps": 6.13}
            result = srv.get_financials("AAPL")
        assert set(result) == {"ticker", "trailing_eps", "annual"}

    def test_annual_list_has_four_entries(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {}
            result = srv.get_financials("AAPL")
        assert len(result["annual"]) == 4

    def test_annual_record_has_correct_keys(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {}
            result = srv.get_financials("AAPL")
        expected = {"year", "revenue", "net_income", "gross_profit"}
        assert all(set(r) == expected for r in result["annual"])

    def test_fiscal_years_are_correct(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {}
            result = srv.get_financials("AAPL")
        years = [r["year"] for r in result["annual"]]
        assert years == [2023, 2022, 2021, 2020]

    def test_revenue_values_are_correct(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {}
            result = srv.get_financials("AAPL")
        assert result["annual"][0]["revenue"] == 383_285_000_000
        assert result["annual"][0]["net_income"] == 96_995_000_000
        assert result["annual"][0]["gross_profit"] == 169_148_000_000

    def test_trailing_eps_is_included(self, no_cache):
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {"trailingEps": 6.13}
            result = srv.get_financials("AAPL")
        assert result["trailing_eps"] == 6.13

    def test_nan_financial_value_becomes_none(self, no_cache):
        df = _financials_df()
        df.iloc[0, 0] = float("nan")   # Total Revenue for 2023 → NaN
        with patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = df
            mock_yf.return_value.info = {}
            result = srv.get_financials("AAPL")
        assert result["annual"][0]["revenue"] is None

    def test_cache_hit_skips_yfinance(self):
        cached = {"ticker": "AAPL", "trailing_eps": 6.13, "annual": []}
        with patch("server.cache_store.get", return_value=cached), \
             patch("server.yf.Ticker") as mock_yf:
            result = srv.get_financials("AAPL")
        mock_yf.assert_not_called()
        assert result == cached

    def test_cache_miss_stores_result(self):
        with patch("server.cache_store.get", return_value=None), \
             patch("server.cache_store.put") as mock_put, \
             patch("server.yf.Ticker") as mock_yf:
            mock_yf.return_value.financials = _financials_df()
            mock_yf.return_value.info = {"trailingEps": 6.13}
            result = srv.get_financials("TSLA")
        mock_put.assert_called_once_with("financials:TSLA", "financials", result)
