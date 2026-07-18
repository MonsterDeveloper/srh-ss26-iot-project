import { apiRaw } from "~/.server/api.server";
import { privateHeaders } from "~/.server/headers.server";
import { requireSessionUser } from "~/.server/session.server";
import type { Route } from "./+types/resources.experiment-csv";
export async function loader({ request, params }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const response = await apiRaw(
    `/experiments/${params.experimentId}/export`,
    user.username,
  );
  return new Response(response.body, {
    headers: {
      ...privateHeaders,
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="experiment_${params.experimentId}.csv"`,
    },
  });
}
