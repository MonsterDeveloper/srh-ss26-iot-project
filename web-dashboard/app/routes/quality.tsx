import { ExternalLink } from "lucide-react";
import { Form, Link } from "react-router";
import { apiQuery, apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { EmptyState } from "~/components/empty-state";
import { PageHeader } from "~/components/page-header";
import { StatusBadge } from "~/components/status-badge";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Card } from "~/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import { qualityPageSchema } from "~/lib/domain";
import { formatDate } from "~/lib/i18n";
import type { Route } from "./+types/quality";
import { useDashboard } from "./protected-layout";

const FILTERS = [
  "severity",
  "issue",
  "modality",
  "condition",
  "recordingStatus",
  "page",
  "pageSize",
] as const;
export async function loader({ request }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const url = new URL(request.url);
  try {
    return {
      data: await apiRequest(
        apiQuery("/dashboard/quality", url.searchParams, FILTERS),
        { actor: user.username, schema: qualityPageSchema },
      ),
      error: false,
    };
  } catch {
    return { data: null, error: true };
  }
}
export default function Quality({ loaderData }: Route.ComponentProps) {
  const { dictionary: d, locale, metadata } = useDashboard();
  const data = loaderData.data;
  return (
    <div className="space-y-6">
      <PageHeader title={d.quality.title} description={d.quality.subtitle} />
      <Card className="p-5">
        <Form method="get" className="grid grid-cols-6 gap-3">
          <Filter
            name="severity"
            label={d.quality.severity}
            values={[
              ["info", "Info"],
              ["warning", "Warning"],
              ["error", "Error"],
            ]}
          />
          <Filter
            name="modality"
            label={d.quality.modality}
            values={[
              ["motion", d.exercise.motion],
              ["audio", d.exercise.audio],
              ["video", d.exercise.video],
              ["recording", "Recording"],
            ]}
          />
          <Filter
            name="condition"
            label={d.common.condition}
            values={(metadata?.conditions ?? []).map((item) => [
              item.id,
              item.label[locale],
            ])}
          />
          <Filter
            name="recordingStatus"
            label={d.common.status}
            values={Object.entries(d.statuses)}
          />
          <div className="col-span-2 flex justify-end">
            <Button type="submit" variant="outline">
              Apply filters
            </Button>
          </div>
        </Form>
      </Card>
      {loaderData.error || !data ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {d.errors.api}
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState>{d.quality.empty}</EmptyState>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{d.quality.severity}</TableHead>
                <TableHead>{d.quality.issue}</TableHead>
                <TableHead>{d.quality.modality}</TableHead>
                <TableHead>{d.common.patient}</TableHead>
                <TableHead>{d.common.condition}</TableHead>
                <TableHead>{d.common.status}</TableHead>
                <TableHead>{d.common.date}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((issue) => (
                <TableRow key={`${issue.exerciseId}-${issue.code}`}>
                  <TableCell>
                    <Badge
                      variant={
                        issue.severity === "error" ? "destructive" : "secondary"
                      }
                    >
                      {issue.severity}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{issue.issue[locale]}</div>
                    <code className="text-xs text-muted-foreground">
                      {issue.code}
                    </code>
                  </TableCell>
                  <TableCell>{issue.modality}</TableCell>
                  <TableCell>
                    {issue.patientNumber ?? d.common.unlabeled}
                  </TableCell>
                  <TableCell>
                    {metadata?.conditions.find(
                      (item) => item.id === issue.condition,
                    )?.label[locale] ??
                      issue.condition ??
                      "—"}
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={issue.status}
                      label={d.statuses[issue.status]}
                    />
                  </TableCell>
                  <TableCell>{formatDate(issue.createdAt, locale)}</TableCell>
                  <TableCell>
                    <Button
                      render={
                        <Link
                          to={`/experiments/${issue.experimentId}/exercises/${issue.exerciseId}`}
                        />
                      }
                      variant="ghost"
                      size="icon-sm"
                    >
                      <ExternalLink />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
function Filter({
  name,
  label,
  values,
}: {
  name: string;
  label: string;
  values: Array<readonly [string, string]>;
}) {
  return (
    <select
      name={name}
      aria-label={label}
      className="h-8 rounded-lg border bg-white px-2 text-sm"
    >
      <option value="">{label}</option>
      {values.map(([id, text]) => (
        <option key={id} value={id}>
          {text}
        </option>
      ))}
    </select>
  );
}
