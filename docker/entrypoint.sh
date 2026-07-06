#!/bin/sh
set -e

if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
fi

if [ "$1" = "celery" ]; then
  until python manage.py migrate --check > /dev/null 2>&1; do
    echo "Waiting for database migrations..."
    sleep 3
  done
fi

exec "$@"
