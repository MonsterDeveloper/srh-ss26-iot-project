import { Download, Info } from "lucide-react";
import { Form, Link, useLocation } from "react-router";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { apiQuery, apiRequest } from "~/.server/api.server";
import { requireSessionUser } from "~/.server/session.server";
import { PageHeader } from "~/components/page-header";
import { Alert, AlertDescription } from "~/components/ui/alert";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Checkbox } from "~/components/ui/checkbox";
import { Input } from "~/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import {
  describe,
  pairedComparison,
  pearson,
  pooledByCondition,
} from "~/lib/analysis";
import { analysisPageSchema, metadataSchema } from "~/lib/domain";
import { DEFAULT_FEATURES, featureValue } from "~/lib/features";
import { formatNumber } from "~/lib/i18n";
import type { Route } from "./+types/analysis";
import { useDashboard } from "./protected-layout";

const FILTERS = [
  "condition",
  "patientNumber",
  "createdFrom",
  "createdTo",
  "recordingStatus",
  "qualityOnly",
  "feature",
  "page",
  "pageSize",
] as const;
export async function loader({ request }: Route.LoaderArgs) {
  const user = await requireSessionUser(request);
  const url = new URL(request.url);
  if (!url.searchParams.has("pageSize"))
    url.searchParams.set("pageSize", "1000");
  const [data, metadata] = await Promise.all([
    apiRequest(apiQuery("/dashboard/analysis", url.searchParams, FILTERS), {
      actor: user.username,
      schema: analysisPageSchema,
    }),
    apiRequest("/dashboard/metadata", {
      actor: user.username,
      schema: metadataSchema,
    }),
  ]);
  const selected = url.searchParams
    .getAll("feature")
    .filter((id) => metadata.features.some((feature) => feature.id === id));
  const features = selected.length
    ? selected
    : metadata.features
        .filter(
          (feature) =>
            feature.defaultSelected || DEFAULT_FEATURES.includes(feature.id),
        )
        .map((feature) => feature.id);
  return {
    data,
    metadata,
    features,
    paired: Object.fromEntries(
      features.map((id) => [id, pairedComparison(data.items, id)]),
    ),
    pooled: Object.fromEntries(
      features.map((id) => [id, pooledByCondition(data.items, id)]),
    ),
  };
}

const colors = ["#2563eb", "#7c3aed", "#059669", "#db2777"];
export default function Analysis({ loaderData }: Route.ComponentProps) {
  const { dictionary: d, locale } = useDashboard();
  const currentLocation = useLocation();
  const { data, metadata, features } = loaderData;
  const primary = features[0];
  const primaryDef = metadata.features.find((item) => item.id === primary);
  const pooled = loaderData.pooled[primary] ?? [];
  const paired = loaderData.paired[primary];
  const scatterX = features[0];
  const scatterY = features[1] ?? features[0];
  const scatter = data.items.flatMap((item) => {
    const x = featureValue(item, scatterX),
      y = featureValue(item, scatterY);
    return x == null || y == null ? [] : [{ x, y, condition: item.condition }];
  });
  const radar = features.map((id) => {
    const values = data.items.map((item) => featureValue(item, id));
    const stats = describe(values);
    return {
      feature:
        metadata.features.find((item) => item.id === id)?.label[locale] ?? id,
      value: stats.mean ?? 0,
    };
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title={d.analysis.title}
        description={d.analysis.subtitle}
        actions={
          <Button
            render={
              <Link
                reloadDocument
                to={`/resources/analysis.csv${currentLocation.search}`}
              />
            }
            variant="outline"
          >
            <Download />
            {d.common.exportCsv}
          </Button>
        }
      />
      <Alert>
        <Info />
        <AlertDescription>
          {d.analysis.warning} {data.total < 30 ? d.analysis.smallSample : ""}
        </AlertDescription>
      </Alert>
      <Card>
        <CardContent className="pt-5">
          <Form method="get" className="space-y-4">
            <div className="grid grid-cols-5 gap-3">
              <Input name="patientNumber" placeholder={d.common.patient} />
              <Input name="createdFrom" type="date" />
              <Input name="createdTo" type="date" />
              <select
                name="recordingStatus"
                className="h-8 rounded-lg border bg-white px-2 text-sm"
              >
                <option value="">{d.common.status}</option>
                {Object.entries(d.statuses).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox name="qualityOnly" value="true" />
                Quality only
              </label>
            </div>
            <div className="flex flex-wrap gap-3">
              {metadata.features.map((feature) => (
                <label
                  key={feature.id}
                  className="flex items-center gap-2 text-xs"
                >
                  <Checkbox
                    name="feature"
                    value={feature.id}
                    defaultChecked={features.includes(feature.id)}
                  />
                  {feature.label[locale]}
                </label>
              ))}
            </div>
            <div className="flex justify-end">
              <Button type="submit" variant="outline">
                Apply filters
              </Button>
            </div>
          </Form>
        </CardContent>
      </Card>
      <Tabs defaultValue="paired">
        <TabsList>
          <TabsTrigger value="paired">{d.analysis.paired}</TabsTrigger>
          <TabsTrigger value="explore">Explore</TabsTrigger>
          <TabsTrigger value="table">{d.analysis.table}</TabsTrigger>
          <TabsTrigger value="glossary">{d.analysis.glossary}</TabsTrigger>
        </TabsList>
        <TabsContent value="paired" className="mt-5 space-y-5">
          <div className="grid grid-cols-4 gap-4">
            <Stat
              label={d.analysis.matched}
              value={paired?.summary.count ?? 0}
            />
            <Stat
              label={d.analysis.meanDelta}
              value={formatNumber(paired?.summary.mean, locale)}
            />
            <Stat
              label={d.analysis.medianDelta}
              value={formatNumber(paired?.summary.median, locale)}
            />
            <Stat
              label={d.analysis.spread}
              value={formatNumber(paired?.summary.iqr, locale)}
            />
          </div>
          <div className="grid grid-cols-2 gap-5">
            <ChartCard
              title={`${d.analysis.paired} · ${primaryDef?.label[locale] ?? primary}`}
            >
              <BarChart data={paired?.deltas ?? []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="experimentId" hide />
                <YAxis />
                <Tooltip />
                <Bar dataKey="delta" fill="#2563eb" />
              </BarChart>
            </ChartCard>
            <ChartCard
              title={`${d.analysis.pooled} · ${primaryDef?.label[locale] ?? primary}`}
            >
              <BarChart data={pooled}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="condition" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="mean">
                  {pooled.map((_, index) => (
                    <Cell key={index} fill={colors[index % colors.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ChartCard>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Descriptive summary</CardTitle>
            </CardHeader>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{d.common.condition}</TableHead>
                  <TableHead>n</TableHead>
                  <TableHead>Mean</TableHead>
                  <TableHead>Median</TableHead>
                  <TableHead>SD</TableHead>
                  <TableHead>IQR</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pooled.map((row) => (
                  <TableRow key={row.condition}>
                    <TableCell>
                      {metadata.conditions.find(
                        (item) => item.id === row.condition,
                      )?.label[locale] ?? row.condition}
                    </TableCell>
                    <TableCell>{row.count}</TableCell>
                    <TableCell>{formatNumber(row.mean, locale)}</TableCell>
                    <TableCell>{formatNumber(row.median, locale)}</TableCell>
                    <TableCell>
                      {formatNumber(row.standardDeviation, locale)}
                    </TableCell>
                    <TableCell>{formatNumber(row.iqr, locale)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
        <TabsContent value="explore" className="mt-5">
          <div className="grid grid-cols-2 gap-5">
            <ChartCard title={d.analysis.fingerprint}>
              <RadarChart data={radar}>
                <PolarGrid />
                <PolarAngleAxis dataKey="feature" tick={{ fontSize: 10 }} />
                <Radar
                  dataKey="value"
                  stroke="#2563eb"
                  fill="#2563eb"
                  fillOpacity={0.25}
                />
              </RadarChart>
            </ChartCard>
            <ChartCard
              title={`${d.analysis.scatter}: ${scatterX} / ${scatterY}`}
            >
              <ScatterChart>
                <CartesianGrid />
                <XAxis dataKey="x" name={scatterX} />
                <YAxis dataKey="y" name={scatterY} />
                <Tooltip />
                <Scatter data={scatter} fill="#2563eb" />
              </ScatterChart>
            </ChartCard>
          </div>
          <Card className="mt-5">
            <CardHeader>
              <CardTitle>{d.analysis.correlation}</CardTitle>
            </CardHeader>
            <CardContent>
              <div
                className="grid gap-px bg-neutral-200"
                style={{
                  gridTemplateColumns: `repeat(${features.length + 1}, minmax(80px,1fr))`,
                }}
              >
                <div className="bg-white p-2" />
                {features.map((id) => (
                  <div
                    key={id}
                    className="truncate bg-white p-2 text-xs font-medium"
                  >
                    {id}
                  </div>
                ))}
                {features.flatMap((row) => [
                  <div
                    key={`${row}-label`}
                    className="truncate bg-white p-2 text-xs font-medium"
                  >
                    {row}
                  </div>,
                  ...features.map((column) => {
                    const result = pearson(
                      data.items.map((item) => featureValue(item, row)),
                      data.items.map((item) => featureValue(item, column)),
                    );
                    const alpha = Math.abs(result.correlation ?? 0);
                    return (
                      <div
                        key={`${row}-${column}`}
                        className="p-2 text-center text-xs"
                        style={{
                          background: `color-mix(in srgb, ${result.correlation && result.correlation < 0 ? "#dc2626" : "#2563eb"} ${alpha * 70}%, white)`,
                        }}
                      >
                        {formatNumber(result.correlation, locale, 2)}
                        <span className="ml-1 opacity-60">
                          n={result.count}
                        </span>
                      </div>
                    );
                  }),
                ])}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="table" className="mt-5">
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{d.common.patient}</TableHead>
                  <TableHead>{d.common.condition}</TableHead>
                  <TableHead>{d.common.repetition}</TableHead>
                  {features.map((id) => (
                    <TableHead key={id}>
                      {metadata.features.find((item) => item.id === id)?.label[
                        locale
                      ] ?? id}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => (
                  <TableRow key={item.exerciseId}>
                    <TableCell>
                      {item.patientNumber ?? d.common.unlabeled}
                    </TableCell>
                    <TableCell>{item.condition ?? "—"}</TableCell>
                    <TableCell>{item.repetition ?? "—"}</TableCell>
                    {features.map((id) => (
                      <TableCell key={id}>
                        {formatNumber(featureValue(item, id), locale)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
        <TabsContent value="glossary" className="mt-5 grid grid-cols-2 gap-4">
          {metadata.features.map((feature) => (
            <Card key={feature.id}>
              <CardHeader>
                <CardTitle>{feature.label[locale]}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                {feature.description[locale]}
                <div className="mt-3 font-mono text-xs">
                  {feature.id} · {feature.unit ?? "unitless"} ·{" "}
                  {feature.modality}
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-2 text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}
function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactElement;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
