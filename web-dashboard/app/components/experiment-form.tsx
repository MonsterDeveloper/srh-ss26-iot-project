import { Form, Link, useNavigation } from "react-router";

import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import type { Dictionary } from "~/lib/i18n";
import type { Experiment } from "~/lib/domain";

export function ExperimentForm({
  dictionary: d,
  experiment,
  errors,
}: {
  dictionary: Dictionary;
  experiment?: Experiment;
  errors?: Record<string, string>;
}) {
  const navigation = useNavigation();
  return (
    <Form method="post" className="space-y-6">
      <div className="grid grid-cols-2 gap-5">
        <div className="col-span-2 space-y-2">
          <Label htmlFor="patientNumber">{d.common.patient}</Label>
          <Input
            id="patientNumber"
            name="patientNumber"
            defaultValue={experiment?.patientNumber ?? ""}
            aria-invalid={Boolean(errors?.patientNumber)}
          />
          <FieldError value={errors?.patientNumber} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="age">{d.experiments.age}</Label>
          <Input
            id="age"
            name="age"
            type="number"
            min="0"
            max="130"
            defaultValue={experiment?.age ?? ""}
          />
          <FieldError value={errors?.age} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="height">{d.experiments.height}</Label>
          <Input
            id="height"
            name="height"
            type="number"
            min="1"
            max="300"
            step="0.1"
            defaultValue={experiment?.height ?? ""}
          />
          <FieldError value={errors?.height} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="weight">{d.experiments.weight}</Label>
          <Input
            id="weight"
            name="weight"
            type="number"
            min="1"
            max="500"
            step="0.1"
            defaultValue={experiment?.weight ?? ""}
          />
          <FieldError value={errors?.weight} />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button
          render={
            <Link
              to={experiment ? `/experiments/${experiment.id}` : "/experiments"}
            />
          }
          variant="outline"
        >
          {d.common.cancel}
        </Button>
        <Button type="submit" disabled={navigation.state !== "idle"}>
          {d.common.save}
        </Button>
      </div>
    </Form>
  );
}

function FieldError({ value }: { value?: string }) {
  return value ? <p className="text-xs text-destructive">{value}</p> : null;
}
