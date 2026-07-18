import { redirect } from "react-router";
import { privateHeaders } from "~/.server/headers.server";
import { getMediaRedirect } from "~/.server/media.server";
import { requireSessionUser } from "~/.server/session.server";
import type { Route } from "./+types/resources.media";
export async function loader({ request, params }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const media = await getMediaRedirect(
    params.exerciseId,
    params.asset,
    user.username,
  );
  return redirect(media.url, { headers: privateHeaders });
}
