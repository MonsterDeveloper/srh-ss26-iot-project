# Web Dashboard

- This is a server-rendered React Router 8 BFF. The browser talks only to the
  dashboard; API credentials and signed-media discovery stay server-side.
- Keep server-only code in `app/.server/`. Use `api.server.ts` for FastAPI calls
  so the dashboard token, logged-in actor, and request ID are included.
- Validate upstream responses with the Zod schemas in `app/lib/domain.ts`.
- Media routes must preserve the signed path and query while replacing the URL
  origin with `MEDIA_ORIGIN`.
- Add user-facing text to both `app/lib/i18n/en.ts` and `de.ts`.
- The dashboard intentionally shows a desktop-required notice below 1024 px.
- `DASHBOARD_USERS_JSON` contains exactly three Argon2id-backed accounts.

Use direct Bun script commands, except for the build script because `bun build`
is Bun's built-in bundler:

```bash
bun format:check
bun lint
bun typegen
bun typecheck
bun run build
```
