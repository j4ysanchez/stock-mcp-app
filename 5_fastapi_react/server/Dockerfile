# MCP server container — runs FastMCP as an HTTP/SSE service.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py cache.py ./

# SQLite cache lives here; mount a named volume to persist across restarts.
RUN mkdir -p /data
ENV CACHE_DB_PATH=/data/stocks_cache.db
ENV HOST=0.0.0.0
ENV PORT=8001

EXPOSE 8001

CMD ["python", "server.py"]
