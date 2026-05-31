# Platform security

## Authentication

- Single account via `AUTH_USERNAME` and `AUTH_PASSWORD` (Railway environment variables only).
- Server-side sessions (`SessionMiddleware`) with signed cookie `sip_session`.
- Cookie flags: `HttpOnly`, `SameSite=Strict`, `Secure` when `AUTH_COOKIE_SECURE=true`.
- Inactivity timeout: `SESSION_INACTIVITY_MINUTES` (default 30).
- Brute-force: `AUTH_MAX_LOGIN_ATTEMPTS` / `AUTH_LOCKOUT_MINUTES` per client IP.

## Protected surfaces

All routes except:

- `GET /login`
- `GET /health`
- `GET /robots.txt`
- `GET /static/*` (except `/static/index.html`, which redirects to login)
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

## Railway setup

Set these variables in the Railway service (not in source code):

| Variable | Purpose |
|----------|---------|
| `AUTH_USERNAME` | Login username |
| `AUTH_PASSWORD` | Login password |
| `AUTH_SESSION_SECRET` | Session signing key (≥32 chars) |
| `AUTH_COOKIE_SECURE` | `true` on Railway |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Service account JSON (server only) |
| `GOOGLE_SHEET_MIRROR_ID` | Sheet ID (server only) |
| `ANTHROPIC_API_KEY` | AI API key (server only) |

## Secrets not exposed to browser

- Google credentials and spreadsheet IDs are backend-only.
- `/api/seller/status` returns only `loaded`, `loading`, `seller_count`, `last_loaded_at`.
- `/api/seller/debug/{shop_id}` returns 404 unless `ENABLE_SELLER_DEBUG_ENDPOINT=true`.
- OpenAPI docs (`/docs`) are disabled.
