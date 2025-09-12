# ─────────────────────────────────────────────────────────────
# Dockerfile — Production image for GestUnifServ
# Builds a lightweight container running FastAPI with Uvicorn
# ─────────────────────────────────────────────────────────────

# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RISK_CSV_PATH=/etc/app/config/riesgos.csv

# Set work directory
WORKDIR /app

# Install system dependencies (if needed for asyncpg, psycopg, etc.)
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Install runtime dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY src/ ./src/
COPY data/ ./data/

# Expose app port
EXPOSE 8000

# Start FastAPI with Uvicorn
CMD ["uvicorn", "src.risk_api:app", "--host", "0.0.0.0", "--port", "8000"]
