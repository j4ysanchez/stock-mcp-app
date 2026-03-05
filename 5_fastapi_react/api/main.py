"""
FastAPI bridge — Stock Analyst
Connects to the MCP server via HTTP/SSE and exposes a POST /chat SSE endpoint.
The React frontend runs in a separate web container; Vite proxies /api/* → this service.

Architecture:
  React (web)  -->  POST /api/chat (Vite proxy)  -->  /chat (FastAPI)
                                                           |
                                                     Claude + MCP server (port 8001)
"""

import json
import os
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/sse")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

SUPPORTED_TICKERS = ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NFLX", "NVDA", "TSLA"]

SYSTEM_PROMPT = f"""You are a stock analyst assistant specialising in megacap technology stocks.

You have access to real-time and historical data for: {", ".join(SUPPORTED_TICKERS)}.
Use the available tools whenever you need data to answer a question accurately.

Guidelines:
- Format large numbers in billions/millions for readability (e.g. $2.8T, $192B).
- Always state the data period when discussing prices or financials.
- If a user asks about a ticker you don't support, politely say so and list the ones you do.
- Be concise but informative.
"""

# In-memory conversation history keyed by session_id (UUID from client).
sessions: dict[str, list] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mcp_tools_to_anthropic(tools) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# App lifespan — one persistent MCP connection for the process lifetime
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.anthropic = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    async with sse_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            app.state.mcp_session = session
            app.state.mcp_tools = _mcp_tools_to_anthropic(tools_result.tools)
            yield  # app runs here; MCP connection closes on shutdown


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Agentic loop — async generator, yields SSE event dicts
# ---------------------------------------------------------------------------

async def agentic_loop(conversation, mcp_session, anthropic_tools, anthropic_client):
    while True:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=anthropic_tools,
            messages=conversation,
        )

        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")),
                "(no response)",
            )
            conversation.append({"role": "assistant", "content": response.content})
            yield {"type": "text", "text": text}
            yield {"type": "done"}
            break

        if response.stop_reason == "tool_use":
            conversation.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                yield {"type": "tool_call", "name": block.name, "args": block.input}

                mcp_result = await mcp_session.call_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            mcp_result.content[0].text if mcp_result.content else "{}"
                        ),
                    }
                )

            conversation.append({"role": "user", "content": tool_results})
            # Loop back — let Claude process the tool results.

        else:
            yield {"type": "error", "message": f"Unexpected stop_reason: {response.stop_reason}"}
            break


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools(request: Request):
    return [
        {"name": t["name"], "description": t["description"]}
        for t in request.app.state.mcp_tools
    ]


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    async def generate():
        try:
            conversation = sessions.setdefault(req.session_id, [])
            conversation.append({"role": "user", "content": req.message})
            async for event in agentic_loop(
                conversation,
                request.app.state.mcp_session,
                request.app.state.mcp_tools,
                request.app.state.anthropic,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
