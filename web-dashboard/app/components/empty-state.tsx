import { FlaskConical } from "lucide-react";

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-neutral-50 text-sm text-muted-foreground">
      <FlaskConical className="size-7 text-neutral-400" />
      {children}
    </div>
  );
}
