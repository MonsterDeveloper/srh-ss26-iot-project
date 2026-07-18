import type { AnalysisObservation } from "./domain";
import { featureValue } from "./features";

function mean(values: number[]) {
  return values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : null;
}
function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}
function quantile(values: number[], q: number) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * q;
  const lower = Math.floor(index);
  return (
    sorted[lower] + (sorted[Math.ceil(index)] - sorted[lower]) * (index - lower)
  );
}

export function describe(values: Array<number | null | undefined>) {
  const clean = values.filter(
    (value): value is number =>
      typeof value === "number" && Number.isFinite(value),
  );
  const average = mean(clean);
  return {
    count: clean.length,
    mean: average,
    median: median(clean),
    standardDeviation:
      average == null || clean.length < 2
        ? null
        : Math.sqrt(
            clean.reduce((sum, value) => sum + (value - average) ** 2, 0) /
              (clean.length - 1),
          ),
    iqr: clean.length
      ? (quantile(clean, 0.75) ?? 0) - (quantile(clean, 0.25) ?? 0)
      : null,
  };
}

export function pairedComparison(
  observations: AnalysisObservation[],
  featureId: string,
  baseline = "normal",
  comparison = "wide_step",
) {
  const experiments = new Map<string, Map<string, number[]>>();
  for (const observation of observations) {
    const value = featureValue(observation, featureId);
    if (value == null || !observation.condition) continue;
    const conditions =
      experiments.get(observation.experimentId) ?? new Map<string, number[]>();
    const values = conditions.get(observation.condition) ?? [];
    values.push(value);
    conditions.set(observation.condition, values);
    experiments.set(observation.experimentId, conditions);
  }
  const deltas = [...experiments].flatMap(([experimentId, conditions]) => {
    const a = mean(conditions.get(baseline) ?? []);
    const b = mean(conditions.get(comparison) ?? []);
    return a == null || b == null
      ? []
      : [{ experimentId, baseline: a, comparison: b, delta: b - a }];
  });
  return { deltas, summary: describe(deltas.map((item) => item.delta)) };
}

export function pooledByCondition(
  observations: AnalysisObservation[],
  featureId: string,
) {
  const groups = new Map<string, number[]>();
  for (const observation of observations) {
    const value = featureValue(observation, featureId);
    if (value == null || !observation.condition) continue;
    groups.set(observation.condition, [
      ...(groups.get(observation.condition) ?? []),
      value,
    ]);
  }
  return [...groups].map(([condition, values]) => ({
    condition,
    values,
    ...describe(values),
  }));
}

export function pearson(a: Array<number | null>, b: Array<number | null>) {
  const pairs = a.flatMap((value, index) =>
    value != null && b[index] != null
      ? [[value, b[index] as number] as const]
      : [],
  );
  if (pairs.length < 2) return { correlation: null, count: pairs.length };
  const meanA = mean(pairs.map(([value]) => value))!;
  const meanB = mean(pairs.map(([, value]) => value))!;
  const numerator = pairs.reduce(
    (sum, [x, y]) => sum + (x - meanA) * (y - meanB),
    0,
  );
  const denominator = Math.sqrt(
    pairs.reduce((sum, [x]) => sum + (x - meanA) ** 2, 0) *
      pairs.reduce((sum, [, y]) => sum + (y - meanB) ** 2, 0),
  );
  return {
    correlation: denominator ? numerator / denominator : null,
    count: pairs.length,
  };
}
