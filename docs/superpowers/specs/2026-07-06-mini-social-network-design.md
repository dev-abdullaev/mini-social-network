# Mini Social Network — Backend Design Spec

**Date:** 2026-07-06
**Stack:** Python 3.12, Django 5 + DRF, PostgreSQL, Celery + Redis, Docker

## 1. Overview

Backend for a mini social network: users, posts, comments, likes, JWT auth,
email verification (real SMTP via Gmail), background cleanup of stale data.
Implements all Must-have items of the test assignment plus selected Bonus
items: login rate limiting, post TTL cleanup, extended tests, GitHub Actions
CI, pre-commit hooks, real email sending, Swagger docs, multi-stage Docker.

## 2. Project Layout

```
config/              # Django project: settings, urls, celery app, asgi/wsgi
apps/
  core/              # shared: pagination, permissions, throttles, exceptions
  users/             # User model, auth, email verification, cleanup task
  posts/             # Post, Comment, Like, feed endpoint, post TTL task
tests/               # pytest suite (factories, per-app test modules)
```

Settings are env-driven (django-environ or os.environ), split into a single
`config/settings.py` reading from `.env`. `.env.example` committed; `.env`
gitignored.

## 3. Data Model

### User (custom, `AbstractBaseUser` + `PermissionsMixin`)
- `id` UUID pk (default `uuid4`)
- `email` — unique, used for login
- `username` — unique, 3–32 chars, `[A-Za-z0-9_]`
- `full_name` — 2–100 chars, letters (latin/cyrillic), spaces, hyphens
- `is_verified` — bool, default `False`
- `is_active`, `is_staff` — standard Django flags
- `created_at`, `updated_at`
- `USERNAME_FIELD = "email"`; custom `UserManager`

### EmailVerificationToken
- `id` UUID pk
- `user` FK → User (CASCADE)
- `token` — random urlsafe string, unique, indexed
- `created_at`, `expires_at` (created_at + `VERIFICATION_TOKEN_TTL_HOURS`, default 24)
- `used_at` — nullable; set when consumed

### Post
- `id` UUID pk, `author` FK → User (CASCADE)
- `title` — 5–255 chars
- `content` — up to 10 000 chars
- `created_at`, `updated_at`

### Comment
- `id` UUID pk, `post` FK → Post (CASCADE), `author` FK → User (CASCADE)
- `content` — up to 2 000 chars
- `created_at`

### Like
- `id` UUID pk, `user` FK → User (CASCADE), `post` FK → Post (CASCADE)
- `created_at`
- DB-level `UniqueConstraint(user, post)`

## 4. Auth & Permissions

- JWT via `djangorestframework-simplejwt`: access + refresh tokens.
- Login accepts **email or username** + password (custom token serializer).
- Registration creates `is_verified=False` user, hashes password (Django
  default hasher), generates verification token, dispatches Celery task to
  send the verification email via Gmail SMTP.
- Permission matrix:
  - Anonymous: can read posts/comments/feed. 401 on writes.
  - Authenticated unverified: can log in, read, **like/unlike**. 403 on
    creating posts/comments.
  - Verified: full CRUD on own posts/comments.
  - Edit/delete only own entities (`IsOwnerOrReadOnly`); others get 403
    (404 acceptable where object visibility should be hidden — we return 403
    since posts are public).
- Like rules: cannot like own post (403), cannot like twice (409 or 400 —
  we use 400 with a clear message; DB constraint is the backstop).

## 5. Endpoints

Base prefix `/api/`.

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — | returns user data (no password) |
| POST | `/auth/login` | — | returns access+refresh; throttled |
| POST | `/auth/refresh` | — | refresh token |
| GET | `/auth/me` | JWT | current user |
| GET | `/auth/verify-email?token=` | — | marks `is_verified=True` |
| POST | `/auth/resend-verification` | JWT | new token + email |
| PATCH | `/users/me` | JWT | edit `full_name`, `username` |
| GET | `/posts` | — | pagination + search + date filter |
| POST | `/posts` | JWT+verified | |
| GET | `/posts/{id}` | — | includes comments |
| PATCH/DELETE | `/posts/{id}` | JWT, author | |
| GET | `/posts/{id}/comments` | — | paginated |
| POST | `/posts/{id}/comments` | JWT+verified | |
| DELETE | `/posts/{post_id}/comments/{comment_id}` | JWT, comment author | |
| POST | `/posts/{id}/like` | JWT | not own post, once |
| DELETE | `/posts/{id}/like` | JWT | 404 if no like exists |
| GET | `/feed` | — | grouped by user, paginated over users |

### Feed shape
```json
[
  {"username": "kamran",
   "posts": [{"id": "...", "title": "...", "content": "...",
              "likes": ["<user_uuid>", "..."]}]}
]
```
Paginated over **users** (page/page_size). Built with `prefetch_related`
(`posts`, `posts__likes`) — no N+1.

### Pagination / search / filtering
- `PageNumberPagination` with `page` + `page_size` (max cap), applied to
  posts list, comments, feed.
- `?search=` — `icontains` over `title` and `content` (DRF SearchFilter).
- `?date_from=&date_to=` — ISO dates against `created_at` (django-filter).

## 6. Validation

Enforced in serializers (+ model constraints where cheap):
- email format; username 3–32 `[A-Za-z0-9_]+` unique; full_name 2–100
  (letters latin/cyrillic, spaces, hyphens); title 5–255; content ≤10 000;
  comment ≤2 000. Violations → 400 with per-field error messages.

## 7. Background Jobs (Celery + Redis)

- Redis = Celery broker + result backend + Django cache (used by throttling).
- `send_verification_email(user_id, token)` — async task, Gmail SMTP
  (`EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` app-password from env). Retries
  with backoff on SMTP failure.
- `cleanup_unverified_users` — Celery beat, hourly: delete users where
  `is_verified=False` and `created_at < now - UNVERIFIED_USER_TTL_HOURS`
  (default 24). Also exposed as management command
  `python manage.py cleanup_unverified_users` for manual runs.
- `cleanup_old_posts` — Celery beat, daily: delete posts older than
  `POST_TTL_DAYS`. Disabled when `POST_TTL_DAYS` unset/0 (default).

## 8. Rate Limiting (Bonus)

- Login endpoint: DRF `ScopedRateThrottle` (Redis cache backend),
  e.g. `10/min` per IP.
- Failed-login lockout: counter per email in Redis; after
  `LOGIN_MAX_FAILURES` (default 5) consecutive failures → 429 lockout for
  `LOGIN_LOCKOUT_MINUTES` (default 15). Counter resets on success.

## 9. Infrastructure

- **docker-compose:** `db` (postgres:16), `redis` (redis:7), `web`
  (gunicorn), `celery_worker`, `celery_beat`. Healthchecks on db/redis;
  web waits for healthy db, runs migrations on start.
- **Dockerfile:** multi-stage (builder installs wheels → slim runtime),
  non-root user, layer-cached dependency install for fast rebuilds.
- **Swagger:** `drf-spectacular` — `/api/schema/`, `/api/docs/` (Swagger UI
  with JWT authorize button), `/api/redoc/`.
- **Code quality:** ruff (lint + format check) + black; pre-commit config.
- **CI:** GitHub Actions — services postgres+redis, steps: install deps,
  ruff/black check, pytest.
- **README:** one-command run (`docker compose up`), env setup, sample
  requests, Swagger link, project structure.

## 10. Testing (pytest + pytest-django + factory_boy)

- Auth: register success; duplicate email/username → 400; login success;
  protected endpoint with valid / invalid / missing token.
- Permissions: unverified cannot create post/comment (403); non-author
  cannot edit/delete others' entities.
- Likes: cannot like own post; cannot like twice; unlike works.
- Email verification: valid token verifies; expired/used token rejected.
- Cleanup: `cleanup_unverified_users` deletes only stale unverified users.
- Validation: boundary cases for username/title/content lengths.
- Celery tasks tested in eager mode; email backend mocked (locmem) in tests.

## 11. Configuration (env vars)

`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL` (or discrete PG
vars), `REDIS_URL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
`VERIFICATION_TOKEN_TTL_HOURS=24`, `UNVERIFIED_USER_TTL_HOURS=24`,
`POST_TTL_DAYS=0`, `LOGIN_MAX_FAILURES=5`, `LOGIN_LOCKOUT_MINUTES=15`,
`ACCESS_TOKEN_LIFETIME_MIN=30`, `REFRESH_TOKEN_LIFETIME_DAYS=7`.
