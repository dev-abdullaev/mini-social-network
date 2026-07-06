#!/bin/sh
set -e

if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
