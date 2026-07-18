import { redirect, Form } from "react-router";
import { z } from "zod";
import { apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { PageHeader } from "~/components/page-header";
import { Button } from "~/components/ui/button";
import { Card, CardContent } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { exerciseSchema, metadataSchema } from "~/lib/domain";
import type { Route } from "./+types/exercise-new";
import { useDashboard } from "./protected-layout";

export async function loader({ request, params }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const [metadata, exercises] = await Promise.all([
    apiRequest("/dashboard/metadata", {
      actor: user.username,
      schema: metadataSchema,
    }),
    apiRequest(`/experiments/${params.experimentId}/exercises`, {
      actor: user.username,
      schema: z.array(exerciseSchema),
    }),
  ]);
  return { metadata, exercises };
}
export async function action({ request, params }: Route.ActionArgs) {
  const user = await requireSessionUser(request);
  const form = await request.formData();
  const condition = String(form.get("condition") ?? "");
  const repetition = Number(form.get("repetition"));
  const metadata = await apiRequest("/dashboard/metadata", {
    actor: user.username,
    schema: metadataSchema,
  });
  if (
    !metadata.conditions.some((item) => item.id === condition && item.active) ||
    !Number.isInteger(repetition) ||
    repetition < 1
  )
    return { error: "Invalid condition or repetition" };
  const item = await apiRequest(
    `/experiments/${params.experimentId}/exercises`,
    {
      actor: user.username,
      method: "POST",
      body: { condition, repetition, properties: { condition, repetition } },
      schema: exerciseSchema,
    },
  );
  throw redirect(`/experiments/${params.experimentId}/exercises/${item.id}`);
}
export default function NewExercise({
  loaderData,
  actionData,
}: Route.ComponentProps) {
  const { dictionary: d, locale } = useDashboard();
  const conditions = loaderData.metadata.conditions
    .filter((item) => item.active)
    .sort((a, b) => a.order - b.order);
  const suggested = (id: string) =>
    Math.max(
      0,
      ...loaderData.exercises
        .filter((item) => item.condition === id && !item.archivedAt)
        .map((item) => item.repetition ?? 0),
    ) + 1;
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader title={d.exercise.new} />
      <Card>
        <CardContent className="pt-6">
          <Form method="post" className="space-y-5">
            {actionData?.error ? (
              <p className="text-sm text-destructive">{actionData.error}</p>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="condition">{d.common.condition}</Label>
              <select
                id="condition"
                name="condition"
                className="h-9 w-full rounded-lg border bg-white px-3 text-sm"
                required
              >
                {conditions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label[locale]}
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
                defaultValue={suggested(conditions[0]?.id ?? "")}
                required
              />
            </div>
            <div className="flex justify-end">
              <Button type="submit">{d.common.create}</Button>
            </div>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
