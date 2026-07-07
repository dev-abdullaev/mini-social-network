FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements/ requirements/
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements/prod.txt

FROM python:3.12-slim

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=collectstatic-build-only \
    python manage.py collectstatic --noinput
RUN mkdir -p /app/media && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--max-requests", "1000", "--max-requests-jitter", "100", "--timeout", "60"]
