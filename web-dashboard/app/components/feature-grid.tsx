import { Activity, AudioLines, Video } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import type { Metadata } from "~/lib/domain";
import type { Locale } from "~/lib/i18n";
import { formatNumber } from "~/lib/i18n";

const modalityIcon = { motion: Activity, audio: AudioLines, video: Video };

export function FeatureGrid({
  metadata,
  values,
  locale,
}: {
  metadata: Metadata;
  values: Record<string, number | null>;
  locale: Locale;
}) {
  return (
    <div className="grid grid-cols-3 gap-4">
      {(["motion", "audio", "video"] as const).map((modality) => {
        const Icon = modalityIcon[modality];
        return (
          <Card key={modality}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 capitalize">
                <Icon className="size-4 text-blue-700" />
                {modality}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {metadata.features
                .filter((feature) => feature.modality === modality)
                .map((feature) => (
                  <div
                    key={feature.id}
                    className="group flex items-start justify-between gap-3 border-b py-2 last:border-0"
                    title={feature.description[locale]}
                  >
                    <div>
                      <div className="text-sm font-medium">
                        {feature.label[locale]}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {feature.unit ?? ""}
                      </div>
                    </div>
                    <div className="font-mono text-sm tabular-nums">
                      {formatNumber(values[feature.id], locale)}
                    </div>
                  </div>
                ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
