import {
  AlertTriangle,
  Archive,
  Download,
  Pencil,
  Plus,
  RotateCcw,
} from "lucide-react";
import { Form, Link } from "react-router";
import { z } from "zod";

import { apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { PageHeader } from "~/components/page-header";
import { PollWhenActive } from "~/components/poll-when-active";
import { StatusBadge } from "~/components/status-badge";
import { Alert, AlertDescription } from "~/components/ui/alert";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import {
  auditPageSchema,
  exerciseSchema,
  experimentSchema,
} from "~/lib/domain";
import { formatDate, formatNumber } from "~/lib/i18n";
import type { Route } from "./+types/experiment-detail";
import { useDashboard } from "./protected-layout";

export async function loader({ request, params }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const id = params.experimentId;
  const [experiment, exercises, history] = await Promise.all([
    apiRequest(`/experiments/${id}`, {
      actor: user.username,
      schema: experimentSchema,
    }),
    apiRequest(`/experiments/${id}/exercises`, {
      actor: user.username,
      schema: z.array(exerciseSchema),
    }),
    apiRequest(`/audit-events?experimentId=${id}&pageSize=50`, {
      actor: user.username,
      schema: auditPageSchema,
    }).catch(() => null),
  ]);
  return { experiment, exercises, history };
}
export async function action({ request, params }: Route.ActionArgs) {
  const user = await requireSessionUser(request);
  const form = await request.formData();
  const intent = form.get("intent");
  if (intent !== "archive" && intent !== "restore")
    throw new Response("Bad request", { status: 400 });
  await apiRequest(`/experiments/${params.experimentId}/${intent}`, {
    actor: user.username,
    method: "POST",
  });
  return { ok: true };
}

export default function ExperimentDetail({ loaderData }: Route.ComponentProps) {
  const { dictionary: d, locale, metadata } = useDashboard();
  const { experiment, exercises, history } = loaderData;
  const isArchived = Boolean(experiment.archivedAt);
  const active = exercises.some(
    (item) =>
      item.recordingStatus === "recording" ||
      item.recordingStatus === "processing",
  );
  const conditionName = (id: string | null) =>
    metadata?.conditions.find((item) => item.id === id)?.label[locale] ??
    id ??
    "—";
  return (
    <div className="space-y-6">
      <PollWhenActive active={active} interval={10_000} />
      <PageHeader
        title={experiment.patientNumber ?? d.common.unlabeled}
        description={`${d.experiments.hub} · ${formatDate(experiment.createdAt, locale)}`}
        actions={
          <>
            <Button
              render={
                <Link to={`/resources/experiments/${experiment.id}.csv`} />
              }
              variant="outline"
            >
              <Download />
              {d.common.exportCsv}
            </Button>
            <Button
              render={<Link to={`/experiments/${experiment.id}/edit`} />}
              variant="outline"
            >
              <Pencil />
              {d.common.edit}
            </Button>
            <Form method="post">
              <input
                type="hidden"
                name="intent"
                value={isArchived ? "restore" : "archive"}
              />
              <Button
                type="submit"
                variant={isArchived ? "default" : "destructive"}
              >
                {isArchived ? <RotateCcw /> : <Archive />}
                {isArchived ? d.common.restore : d.common.archive}
              </Button>
            </Form>
          </>
        }
      />
      {isArchived ? (
        <Alert>
          <AlertTriangle />
          <AlertDescription>{d.experiments.archiveBanner}</AlertDescription>
        </Alert>
      ) : null}
      <section className="grid grid-cols-[0.7fr_1.3fr] gap-5">
        <Card>
          <CardHeader>
            <CardTitle>{d.experiments.demographics}</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4 text-sm">
            <Datum
              label={d.experiments.age}
              value={formatNumber(experiment.age, locale, 0)}
            />
            <Datum
              label={d.experiments.height}
              value={formatNumber(experiment.height, locale, 1)}
            />
            <Datum
              label={d.experiments.weight}
              value={formatNumber(experiment.weight, locale, 1)}
            />
            <Datum
              label={d.experiments.state}
              value={isArchived ? d.common.archived : d.common.active}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{d.experiments.matrix}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {metadata?.conditions.map((condition) => {
              const reps = exercises
                .filter(
                  (item) => item.condition === condition.id && !item.archivedAt,
                )
                .map((item) => item.repetition)
                .filter(Boolean);
              return (
                <div
                  key={condition.id}
                  className="rounded-lg border bg-neutral-50 px-3 py-2"
                >
                  <div className="text-xs font-medium">
                    {condition.label[locale]}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {reps.length ? reps.join(", ") : "—"}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </section>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{d.experiments.exercises}</CardTitle>
          {!isArchived ? (
            <Button
              render={
                <Link to={`/experiments/${experiment.id}/exercises/new`} />
              }
              size="sm"
            >
              <Plus />
              {d.experiments.addExercise}
            </Button>
          ) : null}
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{d.common.condition}</TableHead>
              <TableHead>{d.common.repetition}</TableHead>
              <TableHead>{d.common.status}</TableHead>
              <TableHead>{d.experiments.created}</TableHead>
              <TableHead>{d.experiments.qualityIssues}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {exercises.map((exercise) => (
              <TableRow key={exercise.id}>
                <TableCell className="font-medium">
                  {conditionName(exercise.condition)}
                </TableCell>
                <TableCell>{exercise.repetition ?? "—"}</TableCell>
                <TableCell>
                  <StatusBadge
                    status={exercise.recordingStatus}
                    label={d.statuses[exercise.recordingStatus]}
                  />
                </TableCell>
                <TableCell>{formatDate(exercise.createdAt, locale)}</TableCell>
                <TableCell>{exercise.qualityIssueCount}</TableCell>
                <TableCell className="text-right">
                  <Button
                    render={
                      <Link
                        to={`/experiments/${experiment.id}/exercises/${exercise.id}`}
                      />
                    }
                    variant="ghost"
                    size="sm"
                  >
                    {d.common.view}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <section className="grid grid-cols-2 gap-5">
        <Card>
          <CardHeader>
            <CardTitle>{d.experiments.metadata}</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-56 overflow-auto rounded-lg bg-neutral-950 p-4 text-xs text-neutral-200">
              {JSON.stringify(experiment.properties, null, 2)}
            </pre>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{d.experiments.history}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {history?.items.map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between border-b pb-3 text-sm last:border-0"
              >
                <div>
                  <span className="font-medium">{event.actor}</span> ·{" "}
                  {event.action}
                  <div className="text-xs text-muted-foreground">
                    {event.changedFields.join(", ")}
                  </div>
                </div>
                <time className="text-xs text-muted-foreground">
                  {formatDate(event.createdAt, locale)}
                </time>
              </div>
            )) ?? <span className="text-sm text-muted-foreground">—</span>}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
function Datum({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}
