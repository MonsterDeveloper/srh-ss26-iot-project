import { z } from "zod";

const userSchema = z.object({
  username: z.string().regex(/^[a-z][a-z0-9_-]{2,31}$/),
  displayName: z.string().trim().min(1).max(100),
  passwordHash: z
    .string()
    .regex(
      /^\$argon2id\$v=\d+\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]+={0,2}\$[A-Za-z0-9+/]+={0,2}$/,
    ),
});

const envSchema = z.object({
  API_BASE_URL: z.string().url(),
  DASHBOARD_HOST: z.string().min(1),
  MEDIA_ORIGIN: z.string().url(),
  DASHBOARD_API_BEARER_TOKEN: z.string().min(32),
  DASHBOARD_SESSION_SECRET: z
    .string()
    .refine(
      (value) => Buffer.byteLength(value, "utf8") >= 32,
      "Must contain at least 32 bytes",
    ),
  DASHBOARD_USERS_JSON: z.string().min(2),
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),
});

function parseUsers(raw: string) {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("DASHBOARD_USERS_JSON must be valid JSON");
  }
  const users = z.array(userSchema).length(3).parse(value);
  if (new Set(users.map((user) => user.username)).size !== users.length) {
    throw new Error("DASHBOARD_USERS_JSON contains duplicate usernames");
  }
  return users;
}

const env = envSchema.parse(process.env);

export const config = Object.freeze({
  apiBaseUrl: env.API_BASE_URL.replace(/\/$/, ""),
  dashboardHost: env.DASHBOARD_HOST,
  mediaOrigin: env.MEDIA_ORIGIN.replace(/\/$/, ""),
  apiToken: env.DASHBOARD_API_BEARER_TOKEN,
  sessionSecret: env.DASHBOARD_SESSION_SECRET,
  users: parseUsers(env.DASHBOARD_USERS_JSON),
  production: env.NODE_ENV === "production",
});

export type DashboardUserConfig = (typeof config.users)[number];
