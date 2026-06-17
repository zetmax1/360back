#!/bin/bash
set -e

echo "Starting deployment entrypoint..."

# Wait for postgres to be ready (optional, but good practice. Alembic will fail if DB isn't ready)
# We assume DB is ready if Docker's healthcheck passed, but just in case:
# sleep 2

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Create default superuser if needed
echo "Verifying default superuser..."
export PYTHONPATH=.
python scripts/create_superuser.py

# Start application
echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
