"use client";

import { useMemo, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { usePortfolioHistory } from "@/hooks/use-api";
import type { ChartPoint } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { formatINR } from "@/lib/utils";

type Unit = "sec" | "min" | "hour" | "day";

const UNITS: { value: Unit; label: string; description: string }[] = [
  { value: "sec", label: "Sec", description: "by second" },
  { value: "min", label: "Min", description: "by minute" },
  { value: "hour", label: "Hour", description: "by hour" },
  { value: "day", label: "Day", description: "by day" },
];

/** Pick a sensible default unit from how much time the data spans. */
function pickUnit(history: ChartPoint[]): Unit {
  if (history.length < 2) return "day";
  const span = history[history.length - 1].ts - history[0].ts; // seconds
  if (span <= 3 * 60) return "sec";
  if (span <= 3 * 3600) return "min";
  if (span <= 3 * 86400) return "hour";
  return "day";
}

/** Compact axis label, scaled to the chosen unit. */
function formatAxis(ts: number, unit: Unit): string {
  const d = new Date(ts * 1000);
  switch (unit) {
    case "sec":
      return d.toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    case "min":
      return d.toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
    case "hour":
      return `${String(d.getHours()).padStart(2, "0")}:00`;
    case "day":
      return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  }
}

/** Full, unambiguous timestamp for the tooltip. */
function formatFull(ts: number): string {
  return new Date(ts * 1000).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border/60 bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <p className="text-muted-foreground">{formatFull(Number(label))}</p>
      <p className="mt-0.5 font-semibold text-foreground">
        {formatINR(payload[0].value as number)}
      </p>
    </div>
  );
}

export function PnlChart() {
  const { data, isLoading } = usePortfolioHistory();
  const history = useMemo<ChartPoint[]>(() => data?.history ?? [], [data]);

  // null = follow the auto-picked unit; a value = user override.
  const [unit, setUnit] = useState<Unit | null>(null);
  const autoUnit = useMemo(() => pickUnit(history), [history]);
  const activeUnit = unit ?? autoUnit;

  // Evenly-spaced ticks anchored on real data points (first & last included)
  // so the axis lines up edge-to-edge instead of drifting at the right.
  const ticks = useMemo(() => {
    if (history.length < 2) return undefined;
    const count = Math.min(5, history.length);
    const step = (history.length - 1) / (count - 1);
    const out: number[] = [];
    for (let i = 0; i < count; i++) out.push(history[Math.round(i * step)].ts);
    return Array.from(new Set(out)); // de-dupe in case of clustering
  }, [history]);

  const description =
    UNITS.find((u) => u.value === activeUnit)?.description ?? "over time";

  return (
    <Card className="h-full border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
        <div className="space-y-1">
          <CardTitle className="text-base">Portfolio Value</CardTitle>
          <CardDescription>Value over time · {description}</CardDescription>
        </div>
        <Tabs
          value={activeUnit}
          onValueChange={(v) => setUnit(v as Unit)}
          className="shrink-0"
        >
          <TabsList className="h-7 gap-0.5 p-0.5">
            {UNITS.map((u) => (
              <TabsTrigger
                key={u.value}
                value={u.value}
                className="h-6 px-2 py-0 text-[11px]"
              >
                {u.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : history.length < 2 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 text-center">
            <div className="rounded-full border border-dashed border-border/60 p-3">
              <span className="block h-2 w-2 rounded-full bg-muted-foreground/40" />
            </div>
            <p className="text-sm text-muted-foreground">
              Chart populates after the first trade
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={history} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="ts"
                type="number"
                domain={["dataMin", "dataMax"]}
                ticks={ticks}
                tickFormatter={(v) => formatAxis(Number(v), activeUnit)}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                tickMargin={8}
                minTickGap={20}
                axisLine={false}
                tickLine={false}
                padding={{ left: 8, right: 12 }}
              />
              <YAxis
                tickFormatter={(v) => `₹${(v / 1000).toFixed(1)}k`}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "hsl(var(--border))" }} />
              <Area
                type="monotone"
                dataKey="value"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                fill="url(#pnlGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
