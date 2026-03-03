# MCP client container — interactive CLI that connects to the server over SSE.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cli.py .

CMD ["python", "cli.py"]
