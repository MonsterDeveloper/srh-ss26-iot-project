import { Badge } from "~/components/ui/badge";
import type { RecordingStatus } from "~/lib/domain";

const styles: Record<RecordingStatus, string> = {
  idle: "bg-neutral-100 text-neutral-600",
  recording: "bg-blue-100 text-blue-700",
  uploaded: "bg-violet-100 text-violet-700",
  processing: "bg-amber-100 text-amber-800",
  completed: "bg-emerald-100 text-emerald-700",
  completed_with_errors: "bg-orange-100 text-orange-800",
  failed: "bg-red-100 text-red-700",
};

export function StatusBadge({
  status,
  label,
}: {
  status: RecordingStatus;
  label: string;
}) {
  return <Badge className={styles[status]}>{label}</Badge>;
}
