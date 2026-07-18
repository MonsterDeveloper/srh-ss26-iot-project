import { createCookie } from "react-router";

import { de } from "./de";
import { en } from "./en";

export type Locale = "en" | "de";
export type Dictionary = typeof en | typeof de;
export const dictionaries = { en, de } as const;

export const localeCookie = createCookie("srh_dashboard_locale", {
  httpOnly: true,
  maxAge: 60 * 60 * 24 * 365,
  path: "/",
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
});

export async function getLocale(request: Request): Promise<Locale> {
  const cookie = await localeCookie.parse(request.headers.get("Cookie"));
  if (cookie === "de" || cookie === "en") return cookie;
  return /^de(?:-|\b)/i.test(request.headers.get("Accept-Language") ?? "")
    ? "de"
    : "en";
}

export function formatDate(
  value: string | Date,
  locale: Locale,
  options?: Intl.DateTimeFormatOptions,
) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Berlin",
    timeZoneName: "short",
    ...options,
  }).format(new Date(value));
}

export function formatNumber(
  value: number | null | undefined,
  locale: Locale,
  maximumFractionDigits = 2,
) {
  return value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-GB", {
        maximumFractionDigits,
      }).format(value);
}
