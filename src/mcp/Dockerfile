FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main_mcp.py .
COPY .env .

CMD ["python", "main_mcp.py"]