"use client";

import { useSignals } from "@/hooks/use-api";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatTs } from "@/lib/utils";
import type { Signal } from "@/lib/api";

function ActionBadge({ action }: { action: Signal["action"] }) {
  const styles = {
    BUY:  "bg-success/15 text-success",
    SELL: "bg-danger/15 text-danger",
    HOLD: "bg-white/5 text-muted",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${styles[action]}`}>
      {action}
    </span>
  );
}

function ScoreBar({ value }: { value: number }) {
  const color = value >= 65 ? "bg-success" : value >= 35 ? "bg-accent" : "bg-danger";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs text-muted w-6">{value.toFixed(0)}</span>
    </div>
  );
}

export function SignalsTable() {
  const { data, isLoading } = useSignals();
  const signals = (data?.signals ?? []).sort((a, b) => b.composite_score - a.composite_score).slice(0, 6);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Last Scan · Top Signals</CardTitle>
          {data?.last_scan_time && (
            <span className="text-xs text-muted">{formatTs(data.last_scan_time)}</span>
          )}
        </div>
      </CardHeader>

      {isLoading ? (
        <div className="space-y-2">
          {[1,2,3].map(i => <div key={i} className="h-8 bg-border rounded animate-pulse" />)}
        </div>
      ) : signals.length === 0 ? (
        <p className="text-muted text-sm py-4 text-center">Awaiting first scan…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left pb-2 font-medium">Symbol</th>
                <th className="text-center pb-2 font-medium">Action</th>
                <th className="text-right pb-2 font-medium">Score</th>
                <th className="text-right pb-2 font-medium hidden md:table-cell">RSI</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.symbol} className="border-b border-border/50 last:border-0">
                  <td className="py-2 font-semibold text-white">{s.symbol.split("/")[0]}</td>
                  <td className="py-2 text-center"><ActionBadge action={s.action} /></td>
                  <td className="py-2"><ScoreBar value={s.composite_score} /></td>
                  <td className="py-2 text-right text-muted text-xs hidden md:table-cell">
                    {(s.details as Record<string, unknown>)?.rsi_value as number ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
