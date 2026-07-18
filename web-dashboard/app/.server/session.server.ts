import { createCookieSessionStorage, redirect } from "react-router";

import { config } from "./config.server";

export type SessionUser = { username: string; displayName: string };
type SessionData = { user: SessionUser };
type SessionFlashData = { error: string };

export const sessionStorage = createCookieSessionStorage<
  SessionData,
  SessionFlashData
>({
  cookie: {
    name: config.production
      ? "__Host-srh_dashboard_session"
      : "srh_dashboard_session",
    httpOnly: true,
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
    sameSite: "lax",
    secrets: [config.sessionSecret],
    secure: config.production,
  },
});

export function safeReturnTo(
  value: FormDataEntryValue | string | null | undefined,
) {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//")
  )
    return "/";
  try {
    const url = new URL(value, "https://dashboard.invalid");
    return url.origin === "https://dashboard.invalid"
      ? `${url.pathname}${url.search}${url.hash}`
      : "/";
  } catch {
    return "/";
  }
}

export async function getSessionUser(request: Request) {
  const session = await sessionStorage.getSession(
    request.headers.get("Cookie"),
  );
  return session.get("user") ?? null;
}

export async function requireSessionUser(request: Request) {
  const user = await getSessionUser(request);
  if (user) return user;
  const url = new URL(request.url);
  const returnTo = safeReturnTo(`${url.pathname}${url.search}`);
  throw redirect(`/login?returnTo=${encodeURIComponent(returnTo)}`);
}

export async function createUserSession(
  request: Request,
  user: SessionUser,
  returnTo: string,
) {
  const session = await sessionStorage.getSession(
    request.headers.get("Cookie"),
  );
  session.set("user", user);
  return redirect(safeReturnTo(returnTo), {
    headers: { "Set-Cookie": await sessionStorage.commitSession(session) },
  });
}

export async function destroyUserSession(request: Request) {
  const session = await sessionStorage.getSession(
    request.headers.get("Cookie"),
  );
  return redirect("/login", {
    headers: { "Set-Cookie": await sessionStorage.destroySession(session) },
  });
}
