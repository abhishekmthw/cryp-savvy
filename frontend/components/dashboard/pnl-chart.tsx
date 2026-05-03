"use client";

import { usePortfolioHistory } from "@/hooks/use-api";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { formatINR } from "@/lib/utils";

function formatDate(ts: number) {
  return new Date(ts * 1000).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

export function PnlChart() {
  const { data, isLoading } = usePortfolioHistory();
  const history = data?.history ?? [];

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Portfolio Value</CardTitle>
      </CardHeader>

      {isLoading ? (
        <div className="h-48 bg-border rounded animate-pulse" />
      ) : history.length < 2 ? (
        <p className="text-muted text-sm py-6 text-center">
          Chart populates after the first trade
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={history} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}   />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="ts"
              tickFormatter={formatDate}
              tick={{ fill: "#64748b", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) => `₹${(v / 1000).toFixed(1)}k`}
              tick={{ fill: "#64748b", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={50}
            />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
              labelStyle={{ color: "#94a3b8", fontSize: 11 }}
              formatter={(v: number) => [formatINR(v), "Value"]}
              labelFormatter={(ts) => formatDate(Number(ts))}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#3b82f6"
              strokeWidth={2}
              fill="url(#pnlGrad)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
