# Stock MCP App — Implementation Plan

## Iterations
| Dir | Transport | Interface | Status |
|---|---|---|---|
| `1_stdio/` | stdio (subprocess) | CLI | built |
| `2_http_cli/` | HTTP/SSE | CLI (2 containers) | built |
| `3_jupyter_notebook/` | HTTP/SSE | Jupyter Notebook | planned |
| `4_fastapi_html/` | HTTP/SSE | FastAPI + vanilla HTML | built |
| `5_fastapi_react/` | HTTP/SSE | FastAPI + React | planned |
| `6_ollama_local/` | HTTP/SSE | FastAPI + React + Ollama (Qwen3.5 9B) | planned |

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

## Phase 3 — `3_jupyter_notebook/` (planned)

### Context

Each phase is self-contained. This phase bundles its own copy of the MCP server
so it can be run without any dependency on other phase directories. The notebook
client connects to the local server over HTTP/SSE — but instead of an
interactive CLI loop, each cell isolates one concept: raw tool invocation,
single-turn Claude queries, and multi-turn conversation.

Key learning: MCP tools can be called directly without Claude. Claude is just
one consumer of the MCP protocol — the notebook makes it easy to inspect tool
schemas, test raw calls, and trace the agentic loop step by step.

### Architecture

```
Jupyter Notebook (localhost)  -->  MCP Server (port 8001/SSE)
  mcp ClientSession                 FastMCP + yfinance + SQLite
  Anthropic SDK (cells 4–5 only)
```

The MCP server runs in Docker; the notebook runs locally and connects to it.

### File Structure

```
3_jupyter_notebook/
├── docker-compose.yml     # spins up the MCP server
├── .env.example
├── server/                # copied from 2_http_cli/server/ — no changes
│   ├── Dockerfile
│   ├── server.py
│   ├── cache.py
│   └── requirements.txt
├── notebook.ipynb         # 5-cell progressive walkthrough
└── requirements.txt       # mcp[cli], anthropic, jupyter  (notebook only)
```

### Notebook Cell Plan

| Cell | Title | What it demonstrates |
|---|---|---|
| 1 | Setup & imports | `sse_client`, `ClientSession`, `Anthropic` imports; env var config |
| 2 | Connect & list tools | `session.initialize()` + `session.list_tools()` — raw MCP tool schemas |
| 3 | Raw tool call (no Claude) | `session.call_tool("get_current_price", {"ticker": "AAPL"})` — MCP without AI |
| 4 | Single-turn Claude query | One `messages.create()` call; resolve one round of `tool_use` blocks |
| 5 | Multi-turn agentic loop | Full loop as a reusable async function; multi-question demo |

### Key Implementation Notes

**Cell 2 — list tools:**
```python
async with sse_client(MCP_SERVER_URL) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.list_tools()
        for tool in result.tools:
            print(f"{tool.name}: {tool.description}")
```

**Cell 3 — raw tool call (Claude not involved):**
```python
async with sse_client(MCP_SERVER_URL) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("get_current_price", {"ticker": "AAPL"})
        print(result.content[0].text)   # raw JSON straight from yfinance
```

**Cell 4 — single-turn query with tool resolution:**
```python
response = anthropic.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    tools=anthropic_tools,
    messages=[{"role": "user", "content": "What is NVDA's current price?"}],
)
# detect tool_use, call session.call_tool(), send result back, get final text
```

### What Changes vs Phase 2

| Concern | Phase 2 | Phase 3 |
|---|---|---|
| Client runtime | Docker container | Local Python / Jupyter |
| Interaction model | Interactive CLI loop | Notebook cells |
| Claude dependency | Required | Optional (Cell 3 skips it) |
| MCP connection scope | Full session | Per cell (new async context) |
| Self-contained | Yes | Yes — own server/ copy + docker-compose |

### Running

```bash
cd 3_jupyter_notebook
cp .env.example .env              # add ANTHROPIC_API_KEY

# 1. Start the local MCP server
docker compose up -d mcp-server

# 2. Install notebook dependencies
pip install -r requirements.txt

# 3. Launch Jupyter
MCP_SERVER_URL=http://localhost:8001/sse \
ANTHROPIC_API_KEY=sk-... \
jupyter notebook notebook.ipynb
```

---

## Phase 4 — `4_fastapi_html/` (planned)

### Context

Each phase is self-contained. This phase bundles its own copy of the MCP server
alongside the FastAPI bridge and a single static `index.html` with vanilla
JavaScript. Two containers total.

Key learning: The FastAPI bridge and SSE streaming to a browser are concepts
that exist independently of React. Validating the full backend with plain HTML
first shrinks the debugging surface area before adding a build toolchain.

### Architecture

```
[api container]                              [server container]
Browser (localhost:8000)                     MCP Server (port 8001/SSE)
  GET /         → index.html (StaticFiles)   FastMCP + yfinance + SQLite
  POST /chat    → SSE stream
                    ↕ sse_client + Anthropic SDK
```

FastAPI serves both the static HTML and the API from the same container.
No separate web container — two services total, same as Phase 2.

### File Structure

```
4_fastapi_html/
├── docker-compose.yml
├── .env.example
├── server/                    # copied from 2_http_cli/server/ — no changes
│   ├── Dockerfile
│   ├── server.py
│   ├── cache.py
│   └── requirements.txt
└── api/                       # FastAPI + static HTML (NEW)
    ├── Dockerfile
    ├── main.py                # lifespan MCP conn, POST /chat SSE, StaticFiles
    ├── static/
    │   └── index.html         # vanilla JS chat UI, ~120 lines
    └── requirements.txt       # fastapi, uvicorn[standard], anthropic, mcp[cli]
```

### FastAPI Bridge (`api/main.py`)

Same lifespan + agentic loop pattern as Phase 5, but simpler — no CORS config
needed because HTML is served from the same origin. `StaticFiles` mounts at
`/` so `GET /` returns `index.html` automatically.

```python
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

The `/chat` route sits above the static mount and takes priority:

```python
@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    async def generate():
        conversation = sessions.setdefault(req.session_id, [])
        conversation.append({"role": "user", "content": req.message})
        async for event in agentic_loop(conversation, request.app.state.mcp_session,
                                        request.app.state.mcp_tools):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**SSE event types** (identical across Phases 4 and 5):

| Event type | Payload | When |
|---|---|---|
| `tool_call` | `{name, args}` | before each MCP tool call |
| `text` | `{text}` | full assistant reply |
| `done` | `{}` | agentic loop complete |
| `error` | `{message}` | any exception |

### Vanilla JS Frontend (`api/static/index.html`)

Single self-contained file, no dependencies, no build step.

Key patterns:
- `sessionId` generated with `crypto.randomUUID()`, stored in `sessionStorage`
- `fetch` + `ReadableStream` to consume the SSE stream (same API React will use)
- Tool calls rendered as inline `<span class="tool-badge">` chips
- Input `disabled` while streaming; re-enabled on `done` event

```javascript
async function sendMessage(text) {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, session_id: sessionId }),
  });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();                       // keep incomplete chunk
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      handleEvent(JSON.parse(part.slice(6)));
    }
  }
}
```

### What Changes vs Phase 3 (Notebook)

| Concern | Phase 3 | Phase 4 |
|---|---|---|
| Client type | Jupyter notebook | Browser (vanilla JS) |
| FastAPI bridge | None | Introduced |
| SSE to browser | No | Yes — `fetch` + `ReadableStream` |
| Session management | Per-cell async context | `sessionStorage` UUID |
| Containers | 1 (server only) | 2 (server + api) |
| Claude required | Optional | Always |

### Running

```bash
cd 4_fastapi_html
cp .env.example .env   # add ANTHROPIC_API_KEY
docker compose up --build
# → Chat UI at http://localhost:8000
# → MCP server at http://localhost:8001
```

---

## Phase 5 — `5_fastapi_react/` (planned)

Each phase is self-contained. This phase bundles its own copies of the MCP
server and the FastAPI bridge. The bridge logic (`main.py`, SSE events, session
management) is carried over from Phase 4 with one change: `StaticFiles` is
dropped and CORS is added, since the frontend now runs in a separate `web/`
container.

### Architecture

```
[web container]          [api container]               [server container]
React (port 5173)  -->  FastAPI bridge (port 8000)  -->  MCP Server (port 8001/SSE)
  fetch + SSE             sse_client + Anthropic SDK        FastMCP + yfinance + SQLite
```

Three Docker containers on `stock_net`.
React proxies `/api/*` → FastAPI via Vite config (no CORS issues in dev).

### File Structure

```
5_fastapi_react/
├── docker-compose.yml
├── .env.example
├── server/                    # copied from 2_http_cli/server/ — no changes
│   ├── Dockerfile
│   ├── server.py
│   ├── cache.py
│   └── requirements.txt
├── api/                       # FastAPI bridge (NEW)
│   ├── Dockerfile
│   ├── main.py                # lifespan MCP conn, /chat SSE, /health, /tools
│   └── requirements.txt       # fastapi, uvicorn[standard], anthropic, mcp[cli], sse-starlette
└── web/                       # React frontend (NEW)
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts         # proxy /api -> http://api:8000
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api.ts             # fetch-based SSE helper
        └── components/
            ├── ChatWindow.tsx
            ├── MessageBubble.tsx
            ├── ToolCallBadge.tsx
            └── ChatInput.tsx
```

### FastAPI Bridge (`api/main.py`)

**MCP lifecycle** — keep one long-lived connection via FastAPI `lifespan`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with sse_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            app.state.mcp_session = session
            app.state.mcp_tools = _mcp_tools_to_anthropic(tools.tools)
            yield  # runs the app; cleanup on shutdown
```

**Session management** — in-memory dict keyed by `session_id` (UUID from client):
```python
sessions: dict[str, list] = {}   # session_id -> conversation history
```

**POST /chat** — streams SSE events back to React:
```python
@app.post("/chat")
async def chat(req: ChatRequest):
    async def generate():
        conversation = sessions.setdefault(req.session_id, [])
        conversation.append({"role": "user", "content": req.message})

        async for event in agentic_loop(conversation, app.state.mcp_session, app.state.mcp_tools):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**SSE event types** emitted by `agentic_loop()`:

| Event type | Payload | When |
|---|---|---|
| `tool_call` | `{name, args}` | before each MCP tool call |
| `text_chunk` | `{text}` | streaming Claude text (if using streaming API) |
| `text` | `{text}` | full assistant reply (non-streaming) |
| `done` | `{}` | agentic loop finished |
| `error` | `{message}` | any exception |

**Other endpoints:**
- `GET /health` → `{"status": "ok"}`
- `GET /tools` → list of MCP tool names + descriptions

### React Frontend

**Component tree:**
```
App (session_id UUID, useState for messages)
└── ChatWindow
    ├── MessageList
    │   └── MessageBubble (role: user | assistant)
    │       └── ToolCallBadge[]  (shown inline for assistant messages)
    └── ChatInput (textarea + send button, disabled while streaming)
```

**`api.ts` — SSE via fetch ReadableStream:**
```typescript
export async function sendMessage(
  message: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void
) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  const reader = res.body!.getReader();
  // decode stream, split on "\n\n", parse JSON from "data: ..." lines
}
```

**Vite proxy** (avoids CORS, works identically in dev and Docker):
```typescript
// vite.config.ts
server: { proxy: { "/api": { target: "http://api:8000", rewrite: p => p.replace(/^\/api/, "") } } }
```

### Docker Compose

```yaml
services:
  mcp-server:   # identical to Phase 2
    build: ./server
    ports: ["8001:8001"]
    volumes: [stock_cache:/data]
    environment: [CACHE_DB_PATH=/data/stocks_cache.db, HOST=0.0.0.0, PORT=8001]
    healthcheck: ...

  api:
    build: ./api
    ports: ["8000:8000"]
    depends_on:
      mcp-server: { condition: service_healthy }
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - MCP_SERVER_URL=http://mcp-server:8001/sse

  web:
    build: ./web
    ports: ["5173:5173"]
    depends_on: [api]

networks:
  default:
    name: stock_net

volumes:
  stock_cache:
```

### What Changes vs Phase 4 (Vanilla HTML)

| Concern | Phase 4 | Phase 5 |
|---|---|---|
| Frontend | Single `index.html`, no build | React + Vite + TypeScript |
| API serving | FastAPI `StaticFiles` | Separate `web/` container |
| Containers | 2 (server + api) | 3 (server + api + web) |
| SSE consumer | Vanilla JS `fetch` loop | Same pattern, typed in `api.ts` |
| Routing / proxy | None needed (same origin) | Vite `server.proxy` → `/api` |
| `api/main.py` | Unchanged except drop `StaticFiles` | Identical logic, CORS added |

### Running

```bash
cd 5_fastapi_react
cp .env.example .env   # add ANTHROPIC_API_KEY
docker compose up --build
# → React at http://localhost:5173
# → FastAPI at http://localhost:8000
# → MCP server at http://localhost:8001
```

---

## Phase 6 — `6_ollama_local/` (planned)

Each phase is self-contained. This phase carries over the Phase 5 React + FastAPI
stack but swaps Claude (Anthropic API) for a locally-hosted **Qwen3.5 9B** model
served by Ollama. No API key is required — inference runs entirely inside Docker.

Key learning: Ollama exposes an OpenAI-compatible API, so the FastAPI agentic loop
changes are minimal. The main shift is in the tool-calling format (OpenAI
`tool_calls` vs Anthropic `tool_use`) and the addition of a fourth container for
Ollama itself.

### Architecture

```
[web container]          [api container]               [server container]     [ollama container]
React (port 5173)  -->  FastAPI bridge (port 8000)  -->  MCP Server (8001)      Ollama (port 11434)
  fetch + SSE             openai SDK → Ollama               FastMCP + yfinance     qwen3.5:9b
                          sse_client → MCP tools             + SQLite
```

Four Docker containers on `stock_net`. The FastAPI bridge calls Ollama at
`http://ollama:11434/v1` using the `openai` Python package — no Anthropic SDK.

### File Structure

```
6_ollama_local/
├── docker-compose.yml
├── .env.example           # no ANTHROPIC_API_KEY; OLLAMA_MODEL instead
├── server/                # copied from 2_http_cli/server/ — no changes
│   ├── Dockerfile
│   ├── server.py
│   ├── cache.py
│   └── requirements.txt
├── api/                   # FastAPI bridge — agentic loop updated for OpenAI format
│   ├── Dockerfile
│   ├── main.py            # lifespan MCP conn, /chat SSE, /health, /tools
│   └── requirements.txt   # fastapi, uvicorn[standard], openai, mcp[cli], sse-starlette
└── web/                   # React frontend — unchanged from Phase 5
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api.ts
        └── components/
            ├── ChatWindow.tsx
            ├── MessageBubble.tsx
            ├── ToolCallBadge.tsx
            └── ChatInput.tsx
```

### FastAPI Bridge (`api/main.py`)

**LLM client** — OpenAI SDK pointed at Ollama's compatible endpoint:
```python
from openai import AsyncOpenAI

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

llm = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")  # key ignored by Ollama
```

**Tool format** — MCP tools converted to OpenAI `function` tool format (not Anthropic):
```python
def _mcp_tools_to_openai(tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in tools
    ]
```

**Agentic loop** — same structure as Phase 5, different response parsing:
```python
async def agentic_loop(conversation, mcp_session, openai_tools):
    while True:
        response = await llm.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=conversation,
            tools=openai_tools,
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            conversation.append(msg)           # assistant turn with tool_calls
            for tc in msg.tool_calls:
                yield {"type": "tool_call", "name": tc.function.name,
                       "args": json.loads(tc.function.arguments)}
                result = await mcp_session.call_tool(
                    tc.function.name,
                    json.loads(tc.function.arguments),
                )
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.content[0].text,
                })
        else:
            conversation.append({"role": "assistant", "content": msg.content})
            yield {"type": "text", "text": msg.content}
            yield {"type": "done"}
            break
```

**SSE event types** — identical to Phase 5 (no frontend change needed):

| Event type | Payload | When |
|---|---|---|
| `tool_call` | `{name, args}` | before each MCP tool call |
| `text` | `{text}` | full assistant reply |
| `done` | `{}` | agentic loop finished |
| `error` | `{message}` | any exception |

### Docker Compose

```yaml
services:
  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 10s
      retries: 10
      start_period: 30s

  mcp-server:           # identical to Phase 5
    build: ./server
    ports: ["8001:8001"]
    volumes: [stock_cache:/data]
    environment: [CACHE_DB_PATH=/data/stocks_cache.db, HOST=0.0.0.0, PORT=8001]
    healthcheck: ...

  api:
    build: ./api
    ports: ["8000:8000"]
    depends_on:
      ollama:     { condition: service_healthy }
      mcp-server: { condition: service_healthy }
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434/v1
      - OLLAMA_MODEL=qwen3.5:9b
      - MCP_SERVER_URL=http://mcp-server:8001/sse

  web:                  # identical to Phase 5
    build: ./web
    ports: ["5173:5173"]
    depends_on: [api]

networks:
  default:
    name: stock_net

volumes:
  stock_cache:
  ollama_data:          # persists downloaded model weights across restarts
```

**Model pull** — on first startup the model must be pulled into the `ollama_data`
volume (~5 GB). Add a one-shot init service or run manually:
```bash
docker compose run --rm ollama ollama pull qwen3.5:9b
```

### What Changes vs Phase 5 (React + Claude)

| Concern | Phase 5 | Phase 6 |
|---|---|---|
| LLM provider | Anthropic API (cloud) | Ollama (local container) |
| SDK | `anthropic` Python package | `openai` Python package → Ollama |
| API key | `ANTHROPIC_API_KEY` required | None — `api_key="ollama"` (placeholder) |
| Tool format | Anthropic `tool_use` blocks | OpenAI `tool_calls` array |
| Tool result format | `tool_result` content block | `role: "tool"` message |
| Containers | 3 | 4 (+ Ollama) |
| Model weights | Remote (Anthropic infra) | Local volume (`ollama_data`) |
| Cold start | Instant | ~30 s first pull; fast after |
| React frontend | Unchanged | Unchanged |

### Running

```bash
cd 6_ollama_local
cp .env.example .env

# Pull the model first (one-time, ~5 GB)
docker compose run --rm ollama ollama pull qwen3.5:9b

# Start all services
docker compose up --build
# → React at http://localhost:5173
# → FastAPI at http://localhost:8000
# → MCP server at http://localhost:8001
# → Ollama at http://localhost:11434
```
