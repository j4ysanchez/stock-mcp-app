# FastAPI bridge container — serves the chat API and static HTML frontend.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY static/ ./static/

ENV MCP_SERVER_URL=http://mcp-server:8001/sse

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
