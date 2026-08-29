#!/bin/sh
set -e

echo "Waiting for Postgres..."
python -c "
import time, sys
import psycopg2
import os
from urllib.parse import urlparse

url = os.environ.get('DATABASE_URL', '').replace('postgresql+asyncpg://', 'postgresql://')
parsed = urlparse(url)

for attempt in range(30):
    try:
        conn = psycopg2.connect(
            dbname=parsed.path.lstrip('/'), user=parsed.username, password=parsed.password,
            host=parsed.hostname, port=parsed.port or 5432,
        )
        conn.close()
        print('Postgres is ready.')
        sys.exit(0)
    except Exception:
        time.sleep(1)
print('Postgres never became ready.', file=sys.stderr)
sys.exit(1)
"

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
