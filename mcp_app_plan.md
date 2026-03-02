# Stock MCP App — Implementation Plan

## Iterations
| Dir | Transport | Interface | Status |
|---|---|---|---|
| `1_stdio/` | stdio (subprocess) | CLI | built |
| `2_http/` | HTTP/SSE | FastAPI + React | planned |

---

## Phase 1 — `1_stdio/`

### Context
Single Docker container. The CLI (MCP client) spawns the MCP server as a stdio
subprocess — the simplest MCP transport. Claude (via Anthropic SDK) acts as the
reasoning layer, calling MCP tools based on user questions. Responses are cached
in SQLite to avoid redundant yfinance API calls.

Tickers: AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA

### Architecture

```
CLI (client/cli.py)  <-->  Claude (claude-sonnet-4-6)
        | stdio subprocess
MCP Server (server/server.py)
        |
yfinance  +  SQLite cache (/data/stocks_cache.db)
```

### File Structure

```
1_stdio/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── server/
│   ├── server.py          # FastMCP — 4 tools
│   ├── cache.py           # SQLite read/write with per-type TTL
│   └── requirements.txt   # mcp, yfinance
└── client/
    ├── cli.py             # interactive loop: input -> Claude -> MCP -> output
    └── requirements.txt   # anthropic, mcp
```

### MCP Server Tools

| Tool | Returns | Cache TTL |
|---|---|---|
| `get_current_price(ticker)` | price, change, change_pct, volume, market_cap | 15 min |
| `get_stock_overview(ticker)` | name, sector, P/E, 52w range, beta, description | 1 hour |
| `get_price_history(ticker, period)` | list of {date,open,high,low,close,volume}; period: 5d/1mo/3mo/1y | 24 hours |
| `get_financials(ticker)` | annual revenue, net_income, gross_profit + trailing EPS | 7 days |

### Running

```bash
# Docker (recommended)
cd 1_stdio
cp .env.example .env   # add ANTHROPIC_API_KEY
docker compose up --build
docker compose run --rm app

# Local (no Docker)
pip install -r server/requirements.txt -r client/requirements.txt
ANTHROPIC_API_KEY=sk-... python client/cli.py
```

---

## Phase 2 — `2_http/` (planned)

Switch MCP transport from stdio to HTTP/SSE so server and client run as separate
containers. Add FastAPI REST bridge and React chat frontend.

```
React (port 5173)  ->  FastAPI bridge (port 8000)  ->  MCP Server (port 8001/SSE)
```
