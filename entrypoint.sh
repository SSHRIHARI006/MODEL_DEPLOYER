#!/bin/sh
set -e

if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
  python - <<'PY'
import os
import time

import psycopg2

for attempt in range(30):
    try:
        connection = psycopg2.connect(
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ.get("POSTGRES_HOST", "db"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
        )
        connection.close()
        break
    except psycopg2.OperationalError:
        if attempt == 29:
            raise
        time.sleep(2)
PY
  python manage.py migrate --noinput
fi

exec "$@"
