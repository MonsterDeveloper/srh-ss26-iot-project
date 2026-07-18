import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";

export function SignalChart({
  title,
  time = [],
  series = [],
  color = "#2563eb",
  markers = [],
}: {
  title: string;
  time?: Array<number | null>;
  series?: Array<number | null>;
  color?: string;
  markers?: Array<number | null>;
}) {
  const data = time.map((value, index) => ({
    time: value,
    value: series[index],
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={45} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={1.5}
              dot={false}
              connectNulls={false}
            />
            {markers
              .filter((value): value is number => value != null)
              .map((value, index) => (
                <ReferenceLine
                  key={index}
                  x={value}
                  stroke="#94a3b8"
                  strokeDasharray="2 2"
                />
              ))}
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
