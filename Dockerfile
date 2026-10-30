FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080
# Host and port come from the PORT env var (see garmin_mcp_server.py), not argv.
CMD ["python", "garmin_mcp_server.py"]