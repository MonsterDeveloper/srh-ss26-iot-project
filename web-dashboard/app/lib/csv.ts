import { stringify } from "csv-stringify/sync";

import type { AnalysisObservation } from "./domain";
import { flattenFeatures } from "./features";

export function analysisCsv(items: AnalysisObservation[]) {
  const featureKeys = [
    ...new Set(items.flatMap((item) => Object.keys(flattenFeatures(item)))),
  ].sort();
  const records = items.map((item) => ({
    experiment_id: item.experimentId,
    patient_number: item.patientNumber,
    experiment_created_at: item.experimentCreatedAt,
    age: item.age,
    height_cm: item.height,
    weight_kg: item.weight,
    exercise_id: item.exerciseId,
    condition: item.condition,
    repetition: item.repetition,
    recording_status: item.status,
    archived_at: item.archivedAt,
    quality_issue_codes: item.qualityIssueCodes.join("|"),
    ...Object.fromEntries(
      featureKeys.map((key) => [key, flattenFeatures(item)[key] ?? null]),
    ),
  }));
  return stringify(records, {
    header: true,
    columns: records[0] ? Object.keys(records[0]) : ["experiment_id"],
  });
}
