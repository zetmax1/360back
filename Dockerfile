FROM python:3.12-slim

WORKDIR /app

# Install system deps for python-magic and asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

COPY . .

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Ensure the upload directory exists and is owned by the appuser
RUN mkdir -p /app/uploads && chown -R appuser:appgroup /app/uploads /app

# Switch to the non-root user
USER appuser

EXPOSE 8000

# Run migrations, superuser creation, and start the server
ENTRYPOINT ["/app/entrypoint.sh"]

