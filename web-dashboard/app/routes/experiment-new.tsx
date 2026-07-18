import { redirect } from "react-router";
import { apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { experimentFormSchema, fieldErrors } from "~/.server/validation.server";
import { ExperimentForm } from "~/components/experiment-form";
import { PageHeader } from "~/components/page-header";
import { Card, CardContent } from "~/components/ui/card";
import { experimentSchema } from "~/lib/domain";
import type { Route } from "./+types/experiment-new";
import { useDashboard } from "./protected-layout";

export async function action({ request }: Route.ActionArgs) {
  const user = await requireSessionUser(request);
  const result = experimentFormSchema.safeParse(
    Object.fromEntries(await request.formData()),
  );
  if (!result.success) return { errors: fieldErrors(result.error) };
  const experiment = await apiRequest("/experiments", {
    actor: user.username,
    method: "POST",
    body: { ...result.data, properties: {} },
    schema: experimentSchema,
  });
  throw redirect(`/experiments/${experiment.id}`);
}
export default function NewExperiment({ actionData }: Route.ComponentProps) {
  const { dictionary: d } = useDashboard();
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        title={d.experiments.new}
        description={d.experiments.subtitle}
      />
      <Card>
        <CardContent className="pt-6">
          <ExperimentForm dictionary={d} errors={actionData?.errors} />
        </CardContent>
      </Card>
    </div>
  );
}
