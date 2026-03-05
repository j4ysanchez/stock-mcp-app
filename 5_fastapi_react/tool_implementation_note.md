# Tool Call Implementation Note

## Current behaviour — sequential execution

When Claude returns multiple `tool_use` blocks in a single response, the agentic
loop in `api/main.py` executes them one at a time:

```python
for block in response.content:
    if block.type != "tool_use":
        continue
    yield {"type": "tool_call", "name": block.name, "args": block.input}
    mcp_result = await mcp_session.call_tool(block.name, block.input)
    tool_results.append(...)

conversation.append({"role": "user", "content": tool_results})
```

Each `call_tool` is awaited before the next one starts. For a query like
"compare AAPL and MSFT prices", Claude may request both tools in one turn —
but they run back-to-back, not concurrently.

## The gap

The two fetches are independent; there is no reason to wait for the first to
finish before starting the second. Sequential execution means total latency is
the **sum** of all tool call durations instead of the **maximum**.

## How to fix it — `asyncio.gather`

```python
if response.stop_reason == "tool_use":
    conversation.append({"role": "assistant", "content": response.content})

    tool_blocks = [b for b in response.content if b.type == "tool_use"]

    # Emit all tool_call events first so the UI can show them immediately.
    for block in tool_blocks:
        yield {"type": "tool_call", "name": block.name, "args": block.input}

    # Run all MCP calls concurrently.
    results = await asyncio.gather(
        *[mcp_session.call_tool(b.name, b.input) for b in tool_blocks]
    )

    tool_results = [
        {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": res.content[0].text if res.content else "{}",
        }
        for block, res in zip(tool_blocks, results)
    ]
    conversation.append({"role": "user", "content": tool_results})
```

## Trade-offs

| | Sequential (current) | Parallel (`asyncio.gather`) |
|---|---|---|
| Latency (N tools) | sum of all TTLs | max of all TTLs |
| Code complexity | low | low — one `gather` call |
| Error handling | first failure stops the loop | all calls run; failures need per-result checking |
| MCP session safety | no concurrency concern | `ClientSession.call_tool` must be safe to call concurrently — verify with the MCP library version in use |

The fix is straightforward. The main thing to verify before applying it is that
the `mcp` library's `ClientSession` supports concurrent `call_tool` calls on
the same session object (it does as of `mcp>=1.0.0` since each call is an
independent request/response over the SSE channel).
