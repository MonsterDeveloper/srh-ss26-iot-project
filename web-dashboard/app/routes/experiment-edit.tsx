import { redirect } from "react-router";
import { apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { experimentFormSchema, fieldErrors } from "~/.server/validation.server";
import { ExperimentForm } from "~/components/experiment-form";
import { PageHeader } from "~/components/page-header";
import { Card, CardContent } from "~/components/ui/card";
import { experimentSchema } from "~/lib/domain";
import type { Route } from "./+types/experiment-edit";
import { useDashboard } from "./protected-layout";

export async function loader({ request, params }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  return apiRequest(`/experiments/${params.experimentId}`, {
    actor: user.username,
    schema: experimentSchema,
  });
}
export async function action({ request, params }: Route.ActionArgs) {
  const user = await requireSessionUser(request);
  const existing = await apiRequest(`/experiments/${params.experimentId}`, {
    actor: user.username,
    schema: experimentSchema,
  });
  const result = experimentFormSchema.safeParse(
    Object.fromEntries(await request.formData()),
  );
  if (!result.success) return { errors: fieldErrors(result.error) };
  await apiRequest(`/experiments/${params.experimentId}`, {
    actor: user.username,
    method: "PATCH",
    body: { ...result.data, properties: existing.properties },
    schema: experimentSchema,
  });
  throw redirect(`/experiments/${params.experimentId}`);
}
export default function EditExperiment({
  loaderData,
  actionData,
}: Route.ComponentProps) {
  const { dictionary: d } = useDashboard();
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title={d.experiments.edit} />
      <Card>
        <CardContent className="pt-6">
          <ExperimentForm
            dictionary={d}
            experiment={loaderData}
            errors={actionData?.errors}
          />
        </CardContent>
      </Card>
    </div>
  );
}
