import { apiQuery, apiRequest } from "~/.server/api.server";
import { privateHeaders } from "~/.server/headers.server";
import { requireSessionUser } from "~/.server/session.server";
import { analysisCsv } from "~/lib/csv";
import { analysisPageSchema } from "~/lib/domain";
import type { Route } from "./+types/resources.analysis-csv";
const FILTERS = [
  "condition",
  "patientNumber",
  "createdFrom",
  "createdTo",
  "recordingStatus",
  "qualityOnly",
  "feature",
] as const;
export async function loader({ request }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const url = new URL(request.url);
  url.searchParams.set("pageSize", "1000");
  const data = await apiRequest(
    apiQuery("/dashboard/analysis", url.searchParams, [...FILTERS, "pageSize"]),
    { actor: user.username, schema: analysisPageSchema },
  );
  return new Response(analysisCsv(data.items), {
    headers: {
      ...privateHeaders,
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="srh-analysis.csv"',
    },
  });
}
