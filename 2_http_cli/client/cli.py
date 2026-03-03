"""
MCP CLI Client — Stock Analyst
Connects to the MCP server via HTTP/SSE, then runs an interactive chat loop
powered by Claude.  Each turn shows which MCP tools were called so you can
see the protocol in action.

Usage:
    MCP_SERVER_URL=http://localhost:8001/sse python cli.py
"""

import asyncio
import json
import os
import sys

from anthropic import Anthropic
from mcp import ClientSession
from mcp.client.sse import sse_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    sys.exit("Error: ANTHROPIC_API_KEY environment variable is not set.")

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/sse")

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mcp_tools_to_anthropic(tools) -> list[dict]:
    """Convert MCP tool definitions to the format Anthropic's API expects."""
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in tools
    ]


def _print_banner(tool_count: int) -> None:
    print()
    print("  Stock Analyst — MCP HTTP/SSE demo")
    print(f"  {tool_count} tools loaded | tickers: {', '.join(SUPPORTED_TICKERS)}")
    print(f"  Server: {MCP_SERVER_URL}")
    print("  Type a question, or 'quit' to exit.")
    print()


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run() -> None:
    anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

    async with sse_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            anthropic_tools = _mcp_tools_to_anthropic(tools_result.tools)

            _print_banner(len(anthropic_tools))

            conversation: list[dict] = []

            while True:
                # ---- Read user input ----
                try:
                    raw = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not raw:
                    continue
                if raw.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                conversation.append({"role": "user", "content": raw})

                # ---- Agentic loop: call Claude, execute tool calls, repeat ----
                while True:
                    response = anthropic.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=4096,
                        system=SYSTEM_PROMPT,
                        tools=anthropic_tools,
                        messages=conversation,
                    )

                    if response.stop_reason == "end_turn":
                        text = next(
                            (b.text for b in response.content if hasattr(b, "text")),
                            "(no text response)",
                        )
                        print(f"\nAssistant: {text}\n")
                        conversation.append(
                            {"role": "assistant", "content": response.content}
                        )
                        break

                    if response.stop_reason == "tool_use":
                        conversation.append(
                            {"role": "assistant", "content": response.content}
                        )

                        tool_results = []
                        for block in response.content:
                            if block.type != "tool_use":
                                continue

                            # Show the MCP call so the learning value is visible.
                            args_str = json.dumps(block.input, separators=(",", ":"))
                            print(f"  [MCP] → {block.name}({args_str})")

                            mcp_result = await session.call_tool(
                                block.name, block.input
                            )
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": (
                                        mcp_result.content[0].text
                                        if mcp_result.content
                                        else "{}"
                                    ),
                                }
                            )

                        conversation.append(
                            {"role": "user", "content": tool_results}
                        )
                        # Loop back — let Claude process the tool results.

                    else:
                        print(f"  [warn] unexpected stop_reason: {response.stop_reason}")
                        break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(run())
