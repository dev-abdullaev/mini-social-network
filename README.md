# Mini Social Network API

Django REST backend: users, posts, comments, likes, JWT auth, email
verification, background cleanup via Celery + Redis.

## Quick start

    cp .env.example .env      # fill EMAIL_HOST_USER / EMAIL_HOST_PASSWORD for real emails
    docker compose up --build

- API: http://localhost:8000/api/
- Swagger UI: http://localhost:8000/api/docs/ (use "Authorize" with `Bearer <access>`)
- ReDoc: http://localhost:8000/api/redoc/

Without Gmail credentials the app logs verification emails to the web
container console instead of sending them.

> Note: Redis is published on host port **6380** (not 6379) locally, to
> avoid clashing with other local Redis instances/containers — see the
> comment in `.env.example`. Inside `docker-compose`, the `web` and
> `celery_*` services still talk to Redis over the container network at
> `redis://redis:6379/0`; only the host-side port publishing is 6380.

## Example requests

    # register
    curl -X POST localhost:8000/api/auth/register/ -H 'Content-Type: application/json' \
      -d '{"email":"a@example.com","username":"alice","full_name":"Alice A","password":"strongPass123"}'

    # login (email or username)
    curl -X POST localhost:8000/api/auth/login/ -H 'Content-Type: application/json' \
      -d '{"email":"a@example.com","password":"strongPass123"}'

    # verify email (token from the email / console log)
    curl 'localhost:8000/api/auth/verify-email/?token=<token>'

    # create a post
    curl -X POST localhost:8000/api/posts/ -H "Authorization: Bearer <access>" \
      -H 'Content-Type: application/json' -d '{"title":"Hello world","content":"first post"}'

    # feed
    curl 'localhost:8000/api/feed/?page=1&page_size=10'

    # posts with search + date filter
    curl 'localhost:8000/api/posts/?search=rust&date_from=2026-01-01T00:00:00Z'

## Endpoints overview

| Method | Path | Auth |
|---|---|---|
| POST | /api/auth/register/ | — |
| POST | /api/auth/login/ | — (throttled) |
| POST | /api/auth/refresh/ | — |
| GET | /api/auth/me/ | JWT |
| GET | /api/auth/verify-email/?token= | — |
| POST | /api/auth/resend-verification/ | JWT |
| PATCH | /api/users/me/ | JWT |
| GET | /api/posts/ | — |
| POST | /api/posts/ | JWT + verified |
| GET | /api/posts/{id}/ | — |
| PATCH/DELETE | /api/posts/{id}/ | JWT, author only |
| GET | /api/posts/{id}/comments/ | — |
| POST | /api/posts/{id}/comments/ | JWT + verified |
| DELETE | /api/posts/{id}/comments/{comment_id}/ | JWT, author only |
| POST/DELETE | /api/posts/{id}/like/ | JWT |
| GET | /api/feed/ | — |
| GET | /api/docs/, /api/redoc/, /api/schema/ | — |

## Project structure

    config/       # settings, urls, celery app
    apps/core/    # shared pagination + permission classes
    apps/users/   # User model, JWT auth, email verification, cleanup task
    apps/posts/   # posts, comments, likes, feed, post TTL task
    tests/        # pytest suite

## Background jobs

- `cleanup_unverified_users` — hourly (Celery beat): deletes unverified users
  older than `UNVERIFIED_USER_TTL_HOURS` (default 24). Manual run:
  `docker compose exec web python manage.py cleanup_unverified_users`
- `cleanup_old_posts` — daily: deletes posts older than `POST_TTL_DAYS`
  (default 0 = disabled).

## Rate limiting

Login is throttled (`LOGIN_THROTTLE_RATE`, default 10/min) and locks an
account identifier for `LOGIN_LOCKOUT_MINUTES` after `LOGIN_MAX_FAILURES`
consecutive failures. Registration and resend-verification are throttled via
`REGISTER_THROTTLE_RATE` (default 10/hour) to prevent email-amplification abuse.

## Makefile shortcuts

Common commands are wrapped in a Makefile — run `make help` for the full
list. The most useful ones:

    make up              # build + start the full stack
    make down            # stop it
    make logs            # tail web logs (logs-worker / logs-beat for celery)
    make migrate         # apply migrations inside the web container
    make superuser       # create a Django superuser
    make services        # start only db + redis (for local development)
    make test            # run the test suite (needs make install + services)
    make lint            # ruff check + format check (same as CI)
    make format          # auto-fix and format
    make cleanup-users   # manually purge stale unverified users

## Running tests locally

    make services        # or: docker compose up -d db redis
    make install         # or: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
    make test            # or: .venv/bin/pytest

Note: running bare `manage.py` commands on the host (outside docker and
pytest) requires `DEBUG=1` or a real `SECRET_KEY` in the environment — the
settings refuse to boot a production-shaped config with the insecure
fallback key.
