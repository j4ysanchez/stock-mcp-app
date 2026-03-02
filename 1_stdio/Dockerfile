# Single-container image: the CLI (MCP client) spawns the MCP server
# as a stdio subprocess, so both live in the same image.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies for both server and client in one layer.
COPY server/requirements.txt server/requirements.txt
COPY client/requirements.txt client/requirements.txt
RUN pip install --no-cache-dir \
    -r server/requirements.txt \
    -r client/requirements.txt

# Copy source.
COPY server/ server/
COPY client/ client/

# SQLite cache lives here; mount a named volume to persist across runs.
RUN mkdir -p /data
ENV CACHE_DB_PATH=/data/stocks_cache.db

CMD ["python", "client/cli.py"]
