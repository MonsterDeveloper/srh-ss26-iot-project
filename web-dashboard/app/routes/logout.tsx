import { destroyUserSession } from "~/.server/session.server";
import type { Route } from "./+types/logout";

export async function action({ request }: Route.ActionArgs) {
  return destroyUserSession(request);
}
export async function loader() {
  return new Response("Method not allowed", {
    status: 405,
    headers: { Allow: "POST" },
  });
}
