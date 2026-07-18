import { randomUUID } from "node:crypto";
import type { ZodType } from "zod";

import { config } from "./config.server";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type ApiOptions<T> = {
  actor: string;
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  schema?: ZodType<T>;
  requestId?: string;
};

export async function apiRequest<T = unknown>(
  path: string,
  options: ApiOptions<T>,
): Promise<T> {
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    method: options.method ?? "GET",
    headers: {
      Authorization: `Bearer ${config.apiToken}`,
      "Content-Type": "application/json",
      "X-Dashboard-Actor": options.actor,
      "X-Request-ID": options.requestId ?? randomUUID(),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(15_000),
  }).catch((cause: unknown) => {
    throw new ApiError(
      503,
      cause instanceof Error ? cause.message : "API unavailable",
    );
  });

  if (!response.ok) {
    let detail = `API request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // Keep the safe generic message; never forward upstream HTML.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json();
  return options.schema ? options.schema.parse(payload) : (payload as T);
}

export async function apiRaw(path: string, actor: string) {
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    headers: {
      Authorization: `Bearer ${config.apiToken}`,
      "X-Dashboard-Actor": actor,
      "X-Request-ID": randomUUID(),
    },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok)
    throw new ApiError(
      response.status,
      `API request failed (${response.status})`,
    );
  return response;
}

export function apiQuery(
  path: string,
  source: URLSearchParams,
  allowed: readonly string[],
) {
  const target = new URL(path, config.apiBaseUrl);
  for (const key of allowed)
    for (const value of source.getAll(key))
      target.searchParams.append(key, value);
  return `${target.pathname}${target.search}`;
}
