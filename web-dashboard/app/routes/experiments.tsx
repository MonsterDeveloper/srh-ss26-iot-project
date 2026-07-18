import { Archive, Eye, Pencil, Plus, RotateCcw } from "lucide-react";
import { Form, Link } from "react-router";

import { apiQuery, apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { EmptyState } from "~/components/empty-state";
import { PageHeader } from "~/components/page-header";
import { Button } from "~/components/ui/button";
import { Card, CardContent } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import { experimentsPageSchema } from "~/lib/domain";
import { formatDate } from "~/lib/i18n";
import type { Route } from "./+types/experiments";
import { useDashboard } from "./protected-layout";

const FILTERS = [
  "patientNumber",
  "createdFrom",
  "createdTo",
  "recordingStatus",
  "condition",
  "archive",
  "page",
  "pageSize",
] as const;
export async function loader({ request }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const url = new URL(request.url);
  try {
    return {
      data: await apiRequest(
        apiQuery("/dashboard/experiments", url.searchParams, FILTERS),
        { actor: user.username, schema: experimentsPageSchema },
      ),
      error: false,
    };
  } catch {
    return { data: null, error: true };
  }
}
export async function action({ request }: Route.ActionArgs) {
  const user = await requireSessionUser(request);
  const form = await request.formData();
  const id = String(form.get("id"));
  const intent = form.get("intent");
  if (!id || (intent !== "archive" && intent !== "restore"))
    throw new Response("Bad request", { status: 400 });
  await apiRequest(`/experiments/${encodeURIComponent(id)}/${intent}`, {
    actor: user.username,
    method: "POST",
  });
  return { ok: true };
}

export default function Experiments({ loaderData }: Route.ComponentProps) {
  const { dictionary: d, locale, metadata } = useDashboard();
  const data = loaderData.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={d.experiments.title}
        description={d.experiments.subtitle}
        actions={
          <Button render={<Link to="/experiments/new" />}>
            <Plus />
            {d.experiments.new}
          </Button>
        }
      />
      <Card>
        <CardContent className="pt-5">
          <Form method="get" className="grid grid-cols-6 gap-3">
            <Input name="patientNumber" placeholder={d.common.patient} />
            <Input name="createdFrom" type="date" />
            <Input name="createdTo" type="date" />
            <NativeSelect
              name="recordingStatus"
              label={d.common.status}
              options={Object.entries(d.statuses)}
            />
            <NativeSelect
              name="condition"
              label={d.common.condition}
              options={(metadata?.conditions ?? []).map((item) => [
                item.id,
                item.label[locale],
              ])}
            />
            <NativeSelect
              name="archive"
              label={d.common.active}
              options={[
                ["active", d.common.active],
                ["archived", d.common.archived],
                ["all", d.common.all],
              ]}
            />
            <div className="col-span-6 flex justify-end">
              <Button type="submit" variant="outline">
                Apply filters
              </Button>
            </div>
          </Form>
        </CardContent>
      </Card>
      {loaderData.error || !data ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {d.errors.api}
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState>{d.experiments.empty}</EmptyState>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{d.common.patient}</TableHead>
                <TableHead>{d.experiments.created}</TableHead>
                <TableHead>{d.experiments.demographics}</TableHead>
                <TableHead>{d.experiments.exercises}</TableHead>
                <TableHead>{d.common.status}</TableHead>
                <TableHead>{d.experiments.qualityIssues}</TableHead>
                <TableHead>{d.experiments.state}</TableHead>
                <TableHead className="text-right">{d.common.actions}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((experiment) => (
                <TableRow key={experiment.id}>
                  <TableCell className="font-medium">
                    {experiment.patientNumber ?? d.common.unlabeled}
                  </TableCell>
                  <TableCell>
                    {formatDate(experiment.createdAt, locale)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {[
                      experiment.age && `${experiment.age}y`,
                      experiment.height && `${experiment.height}cm`,
                      experiment.weight && `${experiment.weight}kg`,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </TableCell>
                  <TableCell>{experiment.exerciseCount}</TableCell>
                  <TableCell className="text-xs">
                    {Object.entries(experiment.statusCounts)
                      .map(([key, value]) => `${key} ${value}`)
                      .join(" · ") || "—"}
                  </TableCell>
                  <TableCell>{experiment.qualityIssueCount}</TableCell>
                  <TableCell>
                    {experiment.archivedAt
                      ? d.common.archived
                      : d.common.active}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        render={<Link to={`/experiments/${experiment.id}`} />}
                        size="icon-sm"
                        variant="ghost"
                        title={d.common.view}
                      >
                        <Eye />
                      </Button>
                      <Button
                        render={
                          <Link to={`/experiments/${experiment.id}/edit`} />
                        }
                        size="icon-sm"
                        variant="ghost"
                        title={d.common.edit}
                      >
                        <Pencil />
                      </Button>
                      <Form method="post">
                        <input type="hidden" name="id" value={experiment.id} />
                        <input
                          type="hidden"
                          name="intent"
                          value={experiment.archivedAt ? "restore" : "archive"}
                        />
                        <Button
                          type="submit"
                          size="icon-sm"
                          variant="ghost"
                          title={
                            experiment.archivedAt
                              ? d.common.restore
                              : d.common.archive
                          }
                        >
                          {experiment.archivedAt ? <RotateCcw /> : <Archive />}
                        </Button>
                      </Form>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="border-t px-4 py-3 text-xs text-muted-foreground">
            {data.total} total · page {data.page}
          </div>
        </Card>
      )}
    </div>
  );
}

function NativeSelect({
  name,
  label,
  options,
}: {
  name: string;
  label: string;
  options: Array<readonly [string, string]>;
}) {
  return (
    <select
      name={name}
      aria-label={label}
      className="h-8 rounded-lg border bg-transparent px-2 text-sm"
    >
      <option value="">{label}</option>
      {options.map(([value, text]) => (
        <option key={value} value={value}>
          {text}
        </option>
      ))}
    </select>
  );
}
