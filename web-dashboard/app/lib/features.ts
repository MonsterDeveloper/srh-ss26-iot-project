import type { AnalysisObservation, Metadata } from "./domain";

export const DEFAULT_FEATURES = [
  "step_regularity",
  "stride_regularity",
  "step_amplitude",
  "mean_loudness",
  "vocal_activity_ratio",
  "mean_mouth_opening",
  "mouth_opening_rate",
];

export function flattenFeatures(observation: AnalysisObservation) {
  return {
    ...observation.features.motion,
    ...observation.features.audio,
    ...observation.features.video,
  };
}

export function featureDefinition(metadata: Metadata, id: string) {
  return metadata.features.find((feature) => feature.id === id);
}

export function featureValue(observation: AnalysisObservation, id: string) {
  return flattenFeatures(observation)[id] ?? null;
}
