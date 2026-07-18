# SRH IoT research dashboard

Server-rendered React Router 8 BFF for the Parkinson movement and voice study. The browser talks only to this dashboard; API credentials and signed-media discovery remain in `app/.server/`.

## Setup

1. Copy `.env.example` to `.env` and provide all values.
2. Generate each account hash with `bun run auth:hash`.
3. Put exactly three lowercase-username accounts in `DASHBOARD_USERS_JSON`.
4. Install with `bun install --frozen-lockfile`.

Development uses `bun run dev`. Production is built with Bun and served with Node 24 through `@react-router/serve`.

## Validation commands

CI runs `bun run format:check`, `bun run lint`, `bun run typegen`, `bun run typecheck`, and `bun run build`.

## Operational notes

- The session cookie is host-only, HTTP-only, SameSite Lax, and secure in production.
- Authenticated responses are private and not cacheable.
- The service requires the dashboard-specific API token, distinct from capture clients.
- Media resource routes replace the API-provided URL origin with `MEDIA_ORIGIN`
  before redirecting, while preserving the signed path and query string.
- Screens narrower than 1024 px receive a desktop-required notice.
