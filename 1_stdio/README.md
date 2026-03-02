# stock-mcp-app

A stock analyst chatbot built with [Model Context Protocol (MCP)](https://modelcontextprotocol.io).
The MCP server exposes 4 tools over **stdio** transport; the CLI client connects Claude to those tools via an agentic loop.

**Supported tickers:** AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- [Node.js](https://nodejs.org/) 18+ — only needed for MCP Inspector
- An [Anthropic API key](https://console.anthropic.com/)

---

## 1. Install dependencies

From the **repo root**, create a shared venv and install all packages:

```bash
uv venv                          # creates .venv/ at repo root
source .venv/bin/activate

uv pip install \
  -r 1_stdio/server/requirements.txt \
  -r 1_stdio/client/requirements.txt
```

---

## 2. Set your API key

```bash
cp 1_stdio/.env.example 1_stdio/.env
# edit 1_stdio/.env and set:
# ANTHROPIC_API_KEY=sk-ant-...
```

Export it in your shell before running anything:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## 3. Run the CLI client

The client automatically spawns the server as a subprocess — you only need to start the client:

```bash
source .venv/bin/activate        # if not already active
python 1_stdio/client/cli.py
```

Example session:

```
  Stock Analyst — MCP stdio demo
  4 tools loaded | tickers: AAPL, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA
  Type a question, or 'quit' to exit.

You: What is NVDA's current price and P/E ratio?
  [MCP] → get_current_price({"ticker":"NVDA"})
  [MCP] → get_stock_overview({"ticker":"NVDA"})

Claude: NVIDIA is currently trading at $875.40 (+2.3%)...
```

Type `quit` or `exit` to end the session.

---

## 4. Run MCP Inspector (optional)

MCP Inspector lets you browse and call tools interactively without Claude.

```bash
npx @modelcontextprotocol/inspector
```

Inspector prints a URL with an auth token — open that exact URL (do **not** navigate to `localhost:5173` directly):

```
MCP Inspector is up and running at http://localhost:5173/?MCP_PROXY_AUTH_TOKEN=...
```

In the Inspector UI, configure the connection:

| Field     | Value                                                              |
|-----------|--------------------------------------------------------------------|
| Transport | STDIO                                                              |
| Command   | `/Users/jsanchez/dev/stock-mcp-app/.venv/bin/python`              |
| Arguments | `/Users/jsanchez/dev/stock-mcp-app/1_stdio/server/server.py`      |

Click **Connect**, then go to the **Tools** tab to call any of the 4 tools.

---

## Project structure

```
stock-mcp-app/
├── .venv/                      # shared virtual environment (created by uv venv)
└── 1_stdio/
    ├── server/
    │   ├── server.py           # FastMCP server — 4 stock tools
    │   ├── cache.py            # SQLite cache (TTL-based)
    │   └── requirements.txt
    ├── client/
    │   ├── cli.py              # interactive CLI + agentic Claude loop
    │   └── requirements.txt
    └── .env.example
```

## Available MCP tools

| Tool                | Description                                  | Cache TTL |
|---------------------|----------------------------------------------|-----------|
| `get_current_price` | Live quote, daily change, volume, market cap | 15 min    |
| `get_stock_overview`| Fundamentals, P/E, 52-week range, sector     | 1 hour    |
| `get_price_history` | Daily OHLCV for 5d / 1mo / 3mo / 1y         | 24 hours  |
| `get_financials`    | Annual revenue, net income, EPS (4 years)    | 7 days    |

