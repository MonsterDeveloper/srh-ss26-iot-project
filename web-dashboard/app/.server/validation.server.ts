import { z } from "zod";

const optionalNumber = (min: number, max: number) =>
  z.preprocess(
    (value) => (value === "" || value == null ? null : Number(value)),
    z.number().min(min).max(max).nullable(),
  );
export const experimentFormSchema = z.object({
  patientNumber: z.preprocess(
    (value) => String(value ?? "").trim() || null,
    z.string().max(100).nullable(),
  ),
  age: optionalNumber(0, 130),
  height: optionalNumber(1, 300),
  weight: optionalNumber(1, 500),
});

export function fieldErrors(error: z.ZodError) {
  return Object.fromEntries(
    error.issues.map((issue) => [String(issue.path[0]), issue.message]),
  );
}
