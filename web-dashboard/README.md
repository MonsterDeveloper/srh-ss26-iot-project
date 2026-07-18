# SRH IoT Research Dashboard

Server-rendered React Router 8 BFF for the Parkinson movement and voice study.
The browser talks only to this dashboard; upstream API credentials and signed
media discovery remain in `app/.server/`.

## Stack

TypeScript, React 19, React Router 8, Bun, Tailwind CSS 4, Base UI, Zod,
Recharts, TanStack Table, remix-auth, and Argon2. Bun installs dependencies and
builds the app; the production server runs on Node 24.

## Project structure

- `app/routes.ts` — route manifest.
- `app/routes/` — loaders, actions, pages, CSV exports, and media resources.
- `app/.server/` — configuration, authentication, sessions, API calls, headers,
  validation, and signed-media handling; this code must remain server-only.
- `app/components/` — shared dashboard components and UI primitives.
- `app/lib/` — domain schemas, analysis/CSV helpers, and English/German i18n.
- `scripts/hash-password.ts` — Argon2id password-hash generator.
- `config/deploy.yml` and `.kamal/` — dashboard Kamal deployment.

## Local setup

1. Copy `.env.example` to `.env` and provide all values.
2. Install dependencies with `bun install --frozen-lockfile`.
3. Generate each account hash with `bun auth:hash`.
4. Put exactly three unique accounts in `DASHBOARD_USERS_JSON`. Usernames must
   be lowercase and password values must be Argon2id hashes.
5. Start the FastAPI service, then start the dashboard with `bun dev`.

| Variable                     | Purpose                                                          |
| ---------------------------- | ---------------------------------------------------------------- |
| `API_BASE_URL`               | FastAPI base URL, such as `http://localhost:8000`                |
| `MEDIA_ORIGIN`               | Browser-reachable RustFS origin, such as `http://localhost:9000` |
| `DASHBOARD_API_BEARER_TOKEN` | Dashboard-only API token; minimum 32 characters                  |
| `DASHBOARD_SESSION_SECRET`   | Session signing secret; minimum 32 bytes                         |
| `DASHBOARD_USERS_JSON`       | Exactly three `{username, displayName, passwordHash}` objects    |
| `NODE_ENV`                   | Optional; `development`, `test`, or `production`                 |

Keep `.env` uncommitted. The dashboard token must match the API's dashboard
token and must differ from the capture-client `API_BEARER_TOKEN`.

## Commands

| Command            | Purpose                                      |
| ------------------ | -------------------------------------------- |
| `bun dev`          | Run the development server on all interfaces |
| `bun auth:hash`    | Generate an Argon2id password hash           |
| `bun format`       | Apply Prettier formatting                    |
| `bun format:check` | Check formatting without writing             |
| `bun lint`         | Run ESLint                                   |
| `bun typegen`      | Generate React Router route types            |
| `bun typecheck`    | Run strict TypeScript checks                 |
| `bun run build`    | Create the production React Router build     |
| `bun start`        | Serve an existing build                      |

Before handing off a change, run:

```bash
bun format:check
bun lint
bun typegen
bun typecheck
bun run build
```

The build script keeps `run` because plain `bun build` selects Bun's built-in
bundler, which expects explicit entrypoints.

## Operational notes

- Authentication uses exactly three configured local accounts and a signed,
  HTTP-only, SameSite Lax, host-only cookie that is secure in production.
- Authenticated responses are private and not cacheable. Protected API calls
  include the logged-in username for audit attribution.
- Media resource routes replace the API-provided URL origin with
  `MEDIA_ORIGIN`, preserving the signed path and query string before redirecting.
- English and German are supported. Times are displayed in Europe/Berlin.
- Screens narrower than 1024 px receive a desktop-required notice.
- `/health` is the unauthenticated production health check.

Production deployment details and secret inventory are documented in the
[root README](../README.md#production-deployment). Agent-specific conventions
are in [`CLAUDE.md`](CLAUDE.md).
