# Stock MCP App — Implementation Plan

## Iterations
| Dir | Transport | Interface | Status |
|---|---|---|---|
| `1_stdio/` | stdio (subprocess) | CLI | built |
| `2_http_cli/` | HTTP/SSE | CLI (2 containers) | built |
| `3_react/` | HTTP/SSE | FastAPI + React | planned |

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

## Phase 2 — `2_http_cli/`

### Context
Switch MCP transport from stdio to HTTP/SSE. Server and client now run as
**separate Docker containers** on a shared Docker network. The CLI is unchanged
from the user's perspective — the only difference is that the MCP client connects
over HTTP instead of spawning a subprocess. SQLite cache stays inside the server
container via a named volume.

Key learning: decoupling the MCP server from the client process, enabling the
server to be a long-running service rather than a short-lived subprocess.

### Architecture

```
[client container]                    [server container]
CLI (client/cli.py)                   MCP Server (server/server.py)
  + Claude (claude-sonnet-4-6)  <-->  FastMCP — HTTP/SSE on :8001
  + MCP SSE client                          |
                                      yfinance  +  SQLite cache (/data/stocks_cache.db)
```

Docker network: `stock_net`
Server exposed at: `http://mcp-server:8001/sse`

### File Structure

```
2_http_cli/
├── docker-compose.yml
├── .env.example
├── server/
│   ├── Dockerfile
│   ├── server.py          # FastMCP — same 4 tools, HTTP/SSE transport
│   ├── cache.py           # unchanged from Phase 1
│   └── requirements.txt   # mcp[cli], yfinance
└── client/
    ├── Dockerfile
    ├── cli.py             # same agentic loop; SSE client instead of stdio
    └── requirements.txt   # anthropic, mcp[cli]
```

### What Changes vs Phase 1

| Concern | Phase 1 | Phase 2 |
|---|---|---|
| MCP transport | stdio subprocess | HTTP/SSE over Docker network |
| Containers | 1 | 2 (client + server) |
| Server lifetime | per CLI session | long-running service |
| Client transport init | `StdioServerParameters` | `sse_client(url)` |
| Server startup | `mcp.run()` default (stdio) | `mcp.run(transport="sse")` |
| Cache volume | shared container fs | named volume on server container |

### MCP Server Tools
Identical to Phase 1 — no tool changes, only transport changes.

| Tool | Returns | Cache TTL |
|---|---|---|
| `get_current_price(ticker)` | price, change, change_pct, volume, market_cap | 15 min |
| `get_stock_overview(ticker)` | name, sector, P/E, 52w range, beta, description | 1 hour |
| `get_price_history(ticker, period)` | list of {date,open,high,low,close,volume}; period: 5d/1mo/3mo/1y | 24 hours |
| `get_financials(ticker)` | annual revenue, net_income, gross_profit + trailing EPS | 7 days |

### Key Implementation Notes

**server/server.py** — configure host/port on the constructor, run with SSE transport:
```python
mcp = FastMCP("Stock Analyst", host=HOST, port=PORT)   # host/port from env vars
mcp.run(transport="sse")
```

**client/cli.py** — swap stdio for SSE client:
```python
from mcp.client.sse import sse_client

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8001/sse")

async with sse_client(MCP_SERVER_URL) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        # ... same agentic loop as Phase 1
```

**docker-compose.yml** — two services, one network:
```yaml
services:
  mcp-server:
    build: ./server
    ports:
      - "8001:8001"
    volumes:
      - stock_cache:/data
    environment:
      - CACHE_DB_PATH=/data/stocks_cache.db

  mcp-client:
    build: ./client
    depends_on:
      - mcp-server
    stdin_open: true
    tty: true
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - MCP_SERVER_URL=http://mcp-server:8001/sse

networks:
  default:
    name: stock_net

volumes:
  stock_cache:
```

### Running

```bash
cd 2_http_cli
cp .env.example .env   # add ANTHROPIC_API_KEY
docker compose up --build -d mcp-server   # start server first
docker compose run --rm mcp-client        # attach interactive CLI
```

---

## Phase 3 — `3_react/` (planned)

Replace the CLI client with a FastAPI bridge and React chat frontend. The MCP
server from Phase 2 is reused unchanged.

```
React (port 5173)  ->  FastAPI bridge (port 8000)  ->  MCP Server (port 8001/SSE)
```
