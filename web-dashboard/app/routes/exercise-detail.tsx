import {
  AlertTriangle,
  Archive,
  Download,
  RotateCcw,
  RotateCw,
  Trash2,
} from "lucide-react";
import { Form, Link } from "react-router";

import { ApiError, apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { FeatureGrid } from "~/components/feature-grid";
import { PageHeader } from "~/components/page-header";
import { PollWhenActive } from "~/components/poll-when-active";
import { SignalChart } from "~/components/signal-chart";
import { StatusBadge } from "~/components/status-badge";
import { Alert, AlertDescription } from "~/components/ui/alert";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import {
  auditPageSchema,
  exerciseSchema,
  metadataSchema,
  recordingDataSchema,
  tracesSchema,
} from "~/lib/domain";
import { formatDate } from "~/lib/i18n";
import type { Route } from "./+types/exercise-detail";
import { useDashboard } from "./protected-layout";

async function optional<T>(promise: Promise<T>) {
  try {
    return await promise;
  } catch {
    return null;
  }
}
export async function loader({ request, params }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const id = params.exerciseId;
  const [exercise, data, traces, history, metadata] = await Promise.all([
    apiRequest(`/exercises/${id}`, {
      actor: user.username,
      schema: exerciseSchema,
    }),
    optional(
      apiRequest(`/exercises/${id}/data`, {
        actor: user.username,
        schema: recordingDataSchema,
      }),
    ),
    optional(
      apiRequest(`/exercises/${id}/traces`, {
        actor: user.username,
        schema: tracesSchema,
      }),
    ),
    optional(
      apiRequest(`/audit-events?exerciseId=${id}&pageSize=50`, {
        actor: user.username,
        schema: auditPageSchema,
      }),
    ),
    apiRequest("/dashboard/metadata", {
      actor: user.username,
      schema: metadataSchema,
    }),
  ]);
  return { exercise, data, traces, history, metadata };
}
export async function action({ request, params }: Route.ActionArgs) {
  const user = await requireSessionUser(request);
  const form = await request.formData();
  const intent = String(form.get("intent"));
  const id = params.exerciseId;
  try {
    if (intent === "retry")
      await apiRequest(`/exercises/${id}/recording/retry`, {
        actor: user.username,
        method: "POST",
      });
    else if (intent === "clear")
      await apiRequest(`/exercises/${id}/data`, {
        actor: user.username,
        method: "DELETE",
      });
    else if (intent === "archive" || intent === "restore")
      await apiRequest(`/exercises/${id}/${intent}`, {
        actor: user.username,
        method: "POST",
      });
    else if (intent === "update") {
      const condition = String(form.get("condition"));
      const repetition = Number(form.get("repetition"));
      if (!condition || !Number.isInteger(repetition) || repetition < 1)
        return { error: "Invalid condition or repetition" };
      await apiRequest(`/exercises/${id}`, {
        actor: user.username,
        method: "PATCH",
        body: { condition, repetition },
        schema: exerciseSchema,
      });
    } else throw new Response("Bad request", { status: 400 });
    return { ok: true };
  } catch (error) {
    if (
      error instanceof ApiError &&
      (error.status === 409 || error.status === 422)
    )
      return { error: error.message };
    throw error;
  }
}

export default function ExerciseDetail({
  loaderData,
  actionData,
}: Route.ComponentProps) {
  const { dictionary: d, locale } = useDashboard();
  const { exercise, data, traces, history, metadata } = loaderData;
  const archived = Boolean(exercise.archivedAt);
  const active =
    exercise.recordingStatus === "recording" ||
    exercise.recordingStatus === "processing";
  const values = {
    ...(data?.features.motion ?? {}),
    ...(data?.features.audio ?? {}),
    ...(data?.features.video ?? {}),
  };
  const condition = metadata.conditions.find(
    (item) => item.id === exercise.condition,
  );
  const motion = traces?.motion ?? {};
  const audio = traces?.audio ?? {};
  const video = traces?.video ?? {};
  return (
    <div className="space-y-6">
      <PollWhenActive active={active} />
      <PageHeader
        title={`${d.exercise.title} · ${condition?.label[locale] ?? exercise.condition ?? "—"} #${exercise.repetition ?? "—"}`}
        description={formatDate(exercise.createdAt, locale)}
        actions={
          <>
            <StatusBadge
              status={exercise.recordingStatus}
              label={d.statuses[exercise.recordingStatus]}
            />
            <Form method="post">
              <input type="hidden" name="intent" value="retry" />
              <Button
                type="submit"
                variant="outline"
                disabled={active || archived}
              >
                <RotateCw />
                {d.exercise.retry}
              </Button>
            </Form>
            <Form method="post">
              <input type="hidden" name="intent" value="clear" />
              <Button
                type="submit"
                variant="outline"
                disabled={!exercise.hasData || archived}
              >
                <Trash2 />
                {d.exercise.clear}
              </Button>
            </Form>
            <Form method="post">
              <input
                type="hidden"
                name="intent"
                value={archived ? "restore" : "archive"}
              />
              <Button
                type="submit"
                variant={archived ? "default" : "destructive"}
              >
                {archived ? <RotateCcw /> : <Archive />}
                {archived ? d.common.restore : d.common.archive}
              </Button>
            </Form>
          </>
        }
      />
      {actionData?.error ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertDescription>{actionData.error}</AlertDescription>
        </Alert>
      ) : null}
      {archived ? (
        <Alert>
          <AlertTriangle />
          <AlertDescription>{d.exercise.archiveBanner}</AlertDescription>
        </Alert>
      ) : null}
      {data && Object.keys(data.errors).length ? (
        <Alert>
          <AlertTriangle />
          <AlertDescription>{d.exercise.partial}</AlertDescription>
        </Alert>
      ) : null}
      <Tabs defaultValue="features">
        <TabsList>
          <TabsTrigger value="features">{d.exercise.features}</TabsTrigger>
          <TabsTrigger value="signals">{d.exercise.signals}</TabsTrigger>
          <TabsTrigger value="history">{d.exercise.history}</TabsTrigger>
        </TabsList>
        <TabsContent value="features" className="mt-5">
          {data ? (
            <FeatureGrid metadata={metadata} values={values} locale={locale} />
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {d.exercise.tracesUnavailable}
              </CardContent>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="signals" className="mt-5 space-y-5">
          {traces ? (
            <>
              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">{d.exercise.motion}</h2>
                  <Button
                    render={
                      <Link
                        reloadDocument
                        to={`/resources/exercises/${exercise.id}/media/motion`}
                      />
                    }
                    variant="outline"
                    size="sm"
                  >
                    <Download />
                    CSV
                  </Button>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <SignalChart
                    title="Acceleration magnitude"
                    time={series(motion, "time")}
                    series={series(
                      motion,
                      "accelerationMagnitude",
                      "acceleration_magnitude",
                    )}
                    markers={series(motion, "strideMarkers", "stride_markers")}
                  />
                  <SignalChart
                    title={d.exercise.spectrum}
                    time={series(motion, "psdFrequency", "psd_frequency")}
                    series={series(motion, "psd")}
                    color="#7c3aed"
                  />
                  <SignalChart
                    title={d.exercise.autocorrelation}
                    time={series(
                      motion,
                      "autocorrelationLag",
                      "autocorrelation_lag",
                    )}
                    series={series(motion, "autocorrelation")}
                    color="#059669"
                  />
                </div>
              </section>
              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">{d.exercise.audio}</h2>
                  <Button
                    render={
                      <Link
                        reloadDocument
                        to={`/resources/exercises/${exercise.id}/media/audio`}
                      />
                    }
                    variant="outline"
                    size="sm"
                  >
                    <Download />
                    WAV
                  </Button>
                </div>
                <audio
                  controls
                  preload="metadata"
                  className="w-full"
                  src={`/resources/exercises/${exercise.id}/media/audio`}
                />
                <div className="grid grid-cols-2 gap-4">
                  <SignalChart
                    title={d.exercise.waveform}
                    time={series(audio, "time", "frameTimes")}
                    series={series(audio, "waveformMax", "loudness")}
                  />
                  <SignalChart
                    title="Loudness timeline"
                    time={series(audio, "frameTimes", "time")}
                    series={series(audio, "loudness")}
                    color="#7c3aed"
                  />
                </div>
              </section>
              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">{d.exercise.video}</h2>
                  <div className="flex gap-2">
                    <Button
                      render={
                        <Link
                          reloadDocument
                          to={`/resources/exercises/${exercise.id}/media/video_playback`}
                        />
                      }
                      variant="outline"
                      size="sm"
                    >
                      <Download />
                      MP4
                    </Button>
                    <Button
                      render={
                        <Link
                          reloadDocument
                          to={`/resources/exercises/${exercise.id}/media/video_source`}
                        />
                      }
                      variant="outline"
                      size="sm"
                    >
                      <Download />
                      H.264
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <video
                    controls
                    preload="metadata"
                    className="aspect-video w-full rounded-lg bg-black"
                    src={`/resources/exercises/${exercise.id}/media/video_playback`}
                  />
                  <SignalChart
                    title={d.exercise.mouth}
                    time={series(video, "frameTimes", "time")}
                    series={series(video, "mouthOpening", "mouth_opening")}
                    markers={series(video, "openingEvents", "opening_events")}
                    color="#db2777"
                  />
                </div>
              </section>
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {d.exercise.tracesUnavailable}
              </CardContent>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="history" className="mt-5">
          <div className="grid grid-cols-2 gap-5">
            <Card>
              <CardHeader>
                <CardTitle>{d.exercise.history}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {history?.items.map((event) => (
                  <div
                    key={event.id}
                    className="flex justify-between gap-4 border-b pb-3 text-sm"
                  >
                    <div>
                      <b>{event.actor}</b> · {event.action}
                      <div className="text-xs text-muted-foreground">
                        {event.changedFields.join(", ")}
                      </div>
                    </div>
                    <time className="shrink-0 text-xs text-muted-foreground">
                      {formatDate(event.createdAt, locale)}
                    </time>
                  </div>
                )) ?? "—"}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>{d.experiments.metadata}</CardTitle>
              </CardHeader>
              <CardContent>
                <Form method="post" className="space-y-4">
                  <input type="hidden" name="intent" value="update" />
                  <div className="space-y-2">
                    <Label htmlFor="condition">{d.common.condition}</Label>
                    <select
                      id="condition"
                      name="condition"
                      defaultValue={exercise.condition ?? ""}
                      className="h-9 w-full rounded-lg border bg-white px-3 text-sm"
                      disabled={archived}
                    >
                      {metadata.conditions
                        .filter(
                          (item) =>
                            item.active || item.id === exercise.condition,
                        )
                        .map((item) => (
                          <option
                            key={item.id}
                            value={item.id}
                            disabled={!item.active}
                          >
                            {item.label[locale]}
                            {!item.active ? " (legacy)" : ""}
                          </option>
                        ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="repetition">{d.common.repetition}</Label>
                    <Input
                      id="repetition"
                      name="repetition"
                      type="number"
                      min="1"
                      defaultValue={exercise.repetition ?? ""}
                      disabled={archived}
                    />
                  </div>
                  <Button type="submit" disabled={archived}>
                    {d.common.save}
                  </Button>
                </Form>
                <pre className="mt-5 max-h-48 overflow-auto rounded-lg bg-neutral-950 p-4 text-xs text-neutral-200">
                  {JSON.stringify(exercise.properties, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
function series(
  record: Record<string, Array<number | null>>,
  ...keys: string[]
) {
  for (const key of keys) if (Array.isArray(record[key])) return record[key];
  return [];
}
