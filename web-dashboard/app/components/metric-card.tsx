import type { LucideIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";

export function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon: LucideIcon;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
        <span className="rounded-md bg-blue-50 p-1.5 text-blue-700">
          <Icon className="size-4" />
        </span>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {detail ? (
          <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
