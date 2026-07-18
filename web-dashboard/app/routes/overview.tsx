import {
  Activity,
  CircleCheckBig,
  FlaskConical,
  Plus,
  ShieldAlert,
  Waves,
} from "lucide-react";
import { Link } from "react-router";

import { apiRequest } from "~/.server/api.server";
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
import { ApiErrorState } from "~/components/api-error";
import { MetricCard } from "~/components/metric-card";
import { PageHeader } from "~/components/page-header";
import { StatusBadge } from "~/components/status-badge";
import { overviewSchema } from "~/lib/domain";
import { formatDate } from "~/lib/i18n";
import type { Route } from "./+types/overview";
import { useDashboard } from "./protected-layout";

export async function loader({ request }: Route.LoaderArgs) {
  const { requireSessionUser } = await import("~/.server/session.server");
  const user = await requireSessionUser(request);
  try {
    return {
      overview: await apiRequest("/dashboard/overview", {
        actor: user.username,
        schema: overviewSchema,
      }),
      error: false,
    };
  } catch {
    return { overview: null, error: true };
  }
}

export default function Overview({ loaderData }: Route.ComponentProps) {
  const { dictionary: d, locale } = useDashboard();
  const data = loaderData.overview;
  return (
    <div className="space-y-7">
      <PageHeader
        title={d.overview.title}
        description={d.overview.subtitle}
        actions={
          <Button render={<Link to="/experiments/new" />}>
            <Plus />
            {d.overview.newExperiment}
          </Button>
        }
      />
      {loaderData.error || !data ? (
        <ApiErrorState
          title={d.errors.generic}
          message={d.errors.api}
          retryLabel={d.common.retry}
        />
      ) : (
        <>
          <section className="grid grid-cols-5 gap-4">
            <MetricCard
              label={d.overview.activeExperiments}
              value={data.activeExperimentCount}
              icon={FlaskConical}
            />
            <MetricCard
              label={d.overview.exercises}
              value={data.exerciseCount}
              icon={Waves}
            />
            <MetricCard
              label={d.overview.completed}
              value={`${data.completedRecordingCount}/${data.totalRecordingCount}`}
              icon={CircleCheckBig}
            />
            <MetricCard
              label={d.overview.activeWork}
              value={data.activeWorkCount}
              icon={Activity}
            />
            <MetricCard
              label={d.overview.issues}
              value={data.qualityIssueCount}
              icon={ShieldAlert}
            />
          </section>
          <section className="grid grid-cols-[1.2fr_0.8fr] gap-5">
            <Card>
              <CardHeader>
                <CardTitle>{d.overview.recentExperiments}</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{d.common.patient}</TableHead>
                      <TableHead>{d.experiments.created}</TableHead>
                      <TableHead>{d.experiments.exercises}</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.recentExperiments.map((experiment) => (
                      <TableRow key={experiment.id}>
                        <TableCell className="font-medium">
                          {experiment.patientNumber ?? d.common.unlabeled}
                        </TableCell>
                        <TableCell>
                          {formatDate(experiment.createdAt, locale)}
                        </TableCell>
                        <TableCell>{experiment.exerciseCount}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            render={
                              <Link to={`/experiments/${experiment.id}`} />
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
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>{d.overview.recentActivity}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {data.recentAuditEvents.map((event) => (
                  <div key={event.id} className="flex gap-3">
                    <div className="mt-1 size-2 rounded-full bg-blue-600" />
                    <div className="min-w-0">
                      <div className="text-sm">
                        <span className="font-medium">{event.actor}</span> ·{" "}
                        {event.action}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {event.targetType} ·{" "}
                        {formatDate(event.createdAt, locale)}
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </section>
          <Card>
            <CardHeader>
              <CardTitle>Recording status</CardTitle>
            </CardHeader>
            <CardContent className="flex gap-6">
              {Object.entries(data.statusCounts).map(([status, count]) => (
                <div key={status} className="flex items-center gap-2">
                  <StatusBadge
                    status={status as keyof typeof d.statuses}
                    label={d.statuses[status as keyof typeof d.statuses]}
                  />
                  <span className="text-sm font-semibold tabular-nums">
                    {count}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
