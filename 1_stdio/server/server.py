"""
MCP Server — Stock Analyst
Transport: stdio (spawned as a subprocess by the MCP client)

Exposes 4 tools:
  get_current_price   – live quote with 15-min cache
  get_stock_overview  – fundamentals with 1-hour cache
  get_price_history   – OHLCV data with 24-hour cache
  get_financials      – annual income statement with 7-day cache
"""

import sys
from pathlib import Path

# Allow running directly (python server.py) from any working directory.
sys.path.insert(0, str(Path(__file__).parent))

import yfinance as yf
from mcp.server.fastmcp import FastMCP

import cache as cache_store

ALLOWED_TICKERS = {"AAPL", "AMZN", "GOOGL", "META", "MSFT", "NFLX", "NVDA", "TSLA"}

mcp = FastMCP("Stock Analyst")


def _validate(ticker: str) -> str:
    t = ticker.upper().strip()
    if t not in ALLOWED_TICKERS:
        raise ValueError(
            f"'{t}' is not supported. Choose from: {sorted(ALLOWED_TICKERS)}"
        )
    return t


# ---------------------------------------------------------------------------
# Tool 1 – Current price
# ---------------------------------------------------------------------------

@mcp.tool()
def get_current_price(ticker: str) -> dict:
    """
    Get the current price, daily change, volume, and market cap for a stock.
    ticker: one of AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA
    """
    ticker = _validate(ticker)
    cached = cache_store.get(f"price:{ticker}", "price")
    if cached:
        return cached

    info = yf.Ticker(ticker).fast_info
    prev_close = info.previous_close or info.last_price
    change = info.last_price - prev_close
    result = {
        "ticker": ticker,
        "price": round(info.last_price, 2),
        "change": round(change, 2),
        "change_pct": round(change / prev_close * 100, 2) if prev_close else None,
        "volume": info.last_volume,
        "market_cap": info.market_cap,
    }
    cache_store.put(f"price:{ticker}", "price", result)
    return result


# ---------------------------------------------------------------------------
# Tool 2 – Company overview
# ---------------------------------------------------------------------------

@mcp.tool()
def get_stock_overview(ticker: str) -> dict:
    """
    Get company overview: name, sector, P/E ratio, 52-week range, dividend yield,
    and a short business description.
    ticker: one of AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA
    """
    ticker = _validate(ticker)
    cached = cache_store.get(f"overview:{ticker}", "overview")
    if cached:
        return cached

    info = yf.Ticker(ticker).info
    result = {
        "ticker": ticker,
        "name": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "description": (info.get("longBusinessSummary") or "")[:600],
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
    }
    cache_store.put(f"overview:{ticker}", "overview", result)
    return result


# ---------------------------------------------------------------------------
# Tool 3 – Price history
# ---------------------------------------------------------------------------

PERIOD_MAP = {
    "5d": "5d",
    "1mo": "1mo",
    "3mo": "3mo",
    "1y": "1y",
}


@mcp.tool()
def get_price_history(ticker: str, period: str = "1mo") -> dict:
    """
    Get historical daily OHLCV data for a stock.
    ticker: one of AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA
    period: one of 5d, 1mo, 3mo, 1y  (default: 1mo)
    Returns a list of {date, open, high, low, close, volume} records.
    """
    ticker = _validate(ticker)
    period = PERIOD_MAP.get(period, "1mo")

    cached = cache_store.get(f"history:{ticker}:{period}", "history")
    if cached:
        return cached

    hist = yf.Ticker(ticker).history(period=period)
    records = [
        {
            "date": date.strftime("%Y-%m-%d"),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": int(row["Volume"]),
        }
        for date, row in hist.iterrows()
    ]

    result = {"ticker": ticker, "period": period, "data": records}
    cache_store.put(f"history:{ticker}:{period}", "history", result)
    return result


# ---------------------------------------------------------------------------
# Tool 4 – Financials
# ---------------------------------------------------------------------------

@mcp.tool()
def get_financials(ticker: str) -> dict:
    """
    Get annual revenue, net income, and trailing EPS for the last 4 fiscal years.
    ticker: one of AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA
    """
    ticker = _validate(ticker)
    cached = cache_store.get(f"financials:{ticker}", "financials")
    if cached:
        return cached

    t = yf.Ticker(ticker)
    # .financials is the annual income statement (columns = fiscal year-end dates)
    stmt = t.financials
    annual = []
    for col in stmt.columns[:4]:
        def _get(label: str):
            # yfinance row labels vary slightly across versions
            for candidate in [label, label.replace(" ", ""), label.title()]:
                if candidate in stmt.index:
                    val = stmt.loc[candidate, col]
                    return None if val != val else int(val)  # NaN → None
            return None

        annual.append(
            {
                "year": col.year,
                "revenue": _get("Total Revenue"),
                "net_income": _get("Net Income"),
                "gross_profit": _get("Gross Profit"),
            }
        )

    result = {
        "ticker": ticker,
        "trailing_eps": t.info.get("trailingEps"),
        "annual": annual,
    }
    cache_store.put(f"financials:{ticker}", "financials", result)
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()  # defaults to stdio transport
