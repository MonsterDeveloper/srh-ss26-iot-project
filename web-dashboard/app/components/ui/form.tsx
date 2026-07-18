import type { ReactNode } from "react";

import { Label } from "./label";

export function FormField({ label, htmlFor, error, children }: { label: string; htmlFor: string; error?: string; children: ReactNode }) {
  return <div className="space-y-2"><Label htmlFor={htmlFor}>{label}</Label>{children}{error ? <p className="text-xs text-destructive">{error}</p> : null}</div>;
}
