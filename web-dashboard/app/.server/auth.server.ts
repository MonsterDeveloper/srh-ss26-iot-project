import { verify } from "@node-rs/argon2";
import { Authenticator } from "remix-auth";
import { FormStrategy } from "remix-auth-form";

import { config } from "./config.server";
import type { SessionUser } from "./session.server";

const DUMMY_HASH =
  "$argon2id$v=19$m=19456,t=2,p=1$c3JoLWRhc2hib2FyZC1kdW1teQ$ZvGCCvyb0yC7zO4QaBC9jW1Q/o+tQ7vz9bgP8eIYC7M";
const WINDOW_MS = 15 * 60 * 1000;
const MAX_FAILURES = 5;
const attempts = new Map<string, { count: number; resetAt: number }>();

export class LoginError extends Error {
  constructor(public code: "invalid" | "limited") {
    super(code);
  }
}

function clientIp(request: Request) {
  return (
    request.headers.get("CF-Connecting-IP") ??
    request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ??
    "unknown"
  );
}

export const authenticator = new Authenticator<SessionUser>();

authenticator.use(
  new FormStrategy(async ({ form, request }) => {
    const username = String(form.get("username") ?? "")
      .trim()
      .toLowerCase();
    const password = String(form.get("password") ?? "");
    const key = `${username}:${clientIp(request)}`;
    const now = Date.now();
    const current = attempts.get(key);
    if (current && current.resetAt > now && current.count >= MAX_FAILURES)
      throw new LoginError("limited");
    if (current && current.resetAt <= now) attempts.delete(key);

    const configured = config.users.find((user) => user.username === username);
    const valid = await verify(
      configured?.passwordHash ?? DUMMY_HASH,
      password,
    ).catch(() => false);
    if (!configured || !valid) {
      const previous = attempts.get(key);
      attempts.set(key, {
        count:
          (previous?.resetAt && previous.resetAt > now ? previous.count : 0) +
          1,
        resetAt:
          previous?.resetAt && previous.resetAt > now
            ? previous.resetAt
            : now + WINDOW_MS,
      });
      throw new LoginError("invalid");
    }
    attempts.delete(key);
    return {
      username: configured.username,
      displayName: configured.displayName,
    };
  }),
  "form",
);
