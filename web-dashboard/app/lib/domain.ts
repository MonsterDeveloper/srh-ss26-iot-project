import { z } from "zod";

export const recordingStatusSchema = z.enum([
  "idle",
  "recording",
  "uploaded",
  "processing",
  "completed",
  "completed_with_errors",
  "failed",
]);
export type RecordingStatus = z.infer<typeof recordingStatusSchema>;

export const conditionSchema = z.object({
  id: z.string(),
  label: z.object({ en: z.string(), de: z.string() }),
  description: z.object({ en: z.string(), de: z.string() }).nullish(),
  active: z.boolean(),
  order: z.number(),
  baseline: z.boolean(),
});

export const featureDefinitionSchema = z.object({
  id: z.string(),
  label: z.object({ en: z.string(), de: z.string() }),
  description: z.object({ en: z.string(), de: z.string() }),
  modality: z.enum(["motion", "audio", "video"]),
  unit: z.string().nullable(),
  direction: z.enum(["higher", "lower", "neutral"]),
  format: z.string(),
  defaultSelected: z.boolean(),
});

export const metadataSchema = z.object({
  conditions: z.array(conditionSchema),
  features: z.array(featureDefinitionSchema),
  qualityThresholds: z.object({
    imuClipFraction: z.number(),
    faceDetectionRatio: z.number(),
    staleMinutes: z.number(),
  }),
  traceSchemaVersion: z.number(),
});

export const experimentSchema = z.object({
  id: z.string(),
  patientNumber: z.string().nullable(),
  height: z.number().nullable(),
  age: z.number().nullable(),
  weight: z.number().nullable(),
  properties: z.record(z.string(), z.unknown()),
  createdAt: z.string(),
  archivedAt: z.string().nullable(),
  archivedBy: z.string().nullable(),
  exerciseCount: z.number().default(0),
  qualityIssueCount: z.number().default(0),
  statusCounts: z.record(z.string(), z.number()).default({}),
});

export const exerciseSchema = z.object({
  id: z.string(),
  experimentId: z.string(),
  recordingStatus: recordingStatusSchema,
  recordingStartedAt: z.string().nullable(),
  recordingEndedAt: z.string().nullable(),
  hasData: z.boolean(),
  properties: z.record(z.string(), z.unknown()),
  condition: z.string().nullable(),
  repetition: z.number().int().positive().nullable(),
  archivedAt: z.string().nullable(),
  archivedBy: z.string().nullable(),
  createdAt: z.string(),
  qualityIssueCount: z.number().default(0),
});

export const auditEventSchema = z.object({
  id: z.string(),
  actor: z.string(),
  action: z.string(),
  targetType: z.string(),
  targetId: z.string(),
  experimentId: z.string().nullable().optional(),
  exerciseId: z.string().nullable().optional(),
  changedFields: z.array(z.string()).default([]),
  createdAt: z.string(),
});

export const qualityIssueSchema = z.object({
  code: z.string(),
  severity: z.enum(["info", "warning", "error"]),
  issue: z.object({ en: z.string(), de: z.string() }),
  modality: z.enum(["motion", "audio", "video", "recording"]),
  experimentId: z.string(),
  exerciseId: z.string(),
  patientNumber: z.string().nullable(),
  condition: z.string().nullable(),
  status: recordingStatusSchema,
  createdAt: z.string(),
});

export const analysisObservationSchema = z.object({
  experimentId: z.string(),
  patientNumber: z.string().nullable(),
  experimentCreatedAt: z.string(),
  age: z.number().nullable(),
  height: z.number().nullable(),
  weight: z.number().nullable(),
  exerciseId: z.string(),
  condition: z.string().nullable(),
  repetition: z.number().nullable(),
  status: recordingStatusSchema,
  archivedAt: z.string().nullable(),
  features: z.object({
    motion: z.record(z.string(), z.number().nullable()).default({}),
    audio: z.record(z.string(), z.number().nullable()).default({}),
    video: z.record(z.string(), z.number().nullable()).default({}),
  }),
  extractionErrors: z.record(z.string(), z.string()).default({}),
  qualityIssueCodes: z.array(z.string()).default([]),
});

const page = <T extends z.ZodType>(item: T) =>
  z.object({
    items: z.array(item),
    page: z.number(),
    pageSize: z.number(),
    total: z.number(),
  });

export const experimentsPageSchema = page(experimentSchema);
export const analysisPageSchema = page(analysisObservationSchema);
export const qualityPageSchema = page(qualityIssueSchema);
export const auditPageSchema = page(auditEventSchema);

export const overviewSchema = z.object({
  activeExperimentCount: z.number(),
  exerciseCount: z.number(),
  completedRecordingCount: z.number(),
  totalRecordingCount: z.number(),
  activeWorkCount: z.number(),
  qualityIssueCount: z.number(),
  statusCounts: z.record(z.string(), z.number()),
  recentExperiments: z.array(experimentSchema),
  recentAuditEvents: z.array(auditEventSchema),
});

export const recordingDataSchema = z.object({
  exerciseId: z.string(),
  recordingId: z.string(),
  status: recordingStatusSchema,
  features: z.object({
    motion: z.record(z.string(), z.number().nullable()).optional(),
    audio: z.record(z.string(), z.number().nullable()).optional(),
    video: z.record(z.string(), z.number().nullable()).optional(),
  }),
  errors: z.record(z.string(), z.string()),
});

const numericSeries = z.array(z.number().nullable()).max(2000);
export const tracesSchema = z.object({
  schemaVersion: z.literal(1),
  motion: z.record(z.string(), numericSeries).optional(),
  audio: z.record(z.string(), numericSeries).optional(),
  video: z.record(z.string(), numericSeries).optional(),
});

export type Metadata = z.infer<typeof metadataSchema>;
export type Experiment = z.infer<typeof experimentSchema>;
export type Exercise = z.infer<typeof exerciseSchema>;
export type AuditEvent = z.infer<typeof auditEventSchema>;
export type QualityIssue = z.infer<typeof qualityIssueSchema>;
export type AnalysisObservation = z.infer<typeof analysisObservationSchema>;
export type Traces = z.infer<typeof tracesSchema>;
