import { redirect } from "react-router";
import { requireSessionUser, safeReturnTo } from "~/.server/session.server";
import { localeCookie } from "~/lib/i18n";
import type { Route } from "./+types/resources.locale";

export async function action({ request }: Route.ActionArgs) {
  await requireSessionUser(request);
  const form = await request.formData();
  const locale = form.get("locale") === "de" ? "de" : "en";
  return redirect(safeReturnTo(form.get("returnTo")), {
    headers: { "Set-Cookie": await localeCookie.serialize(locale) },
  });
}
export function loader() {
  return new Response("Method not allowed", {
    status: 405,
    headers: { Allow: "POST" },
  });
}
