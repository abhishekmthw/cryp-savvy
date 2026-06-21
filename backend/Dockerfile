FROM python:3.11-slim

# Prevent .pyc files and enable unbuffered stdout (essential for container logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer — only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create the data directory so SQLite and logs have a home
RUN mkdir -p data

CMD ["python", "src/runner.py"]
