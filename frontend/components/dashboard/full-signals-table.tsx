"use client";

import { useSignals } from "@/hooks/use-api";
import { Card } from "@/components/ui/card";
import { formatTs } from "@/lib/utils";
import type { Signal } from "@/lib/api";

function ActionBadge({ action }: { action: Signal["action"] }) {
  const styles = {
    BUY:  "bg-success/15 text-success",
    SELL: "bg-danger/15 text-danger",
    HOLD: "bg-white/5 text-muted",
  };
  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${styles[action]}`}>
      {action}
    </span>
  );
}

function Bar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  const color = pct >= 65 ? "bg-success" : pct >= 35 ? "bg-accent" : "bg-danger";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted">{value.toFixed(1)}</span>
    </div>
  );
}

export function FullSignalsTable() {
  const { data, isLoading } = useSignals();
  const signals = [...(data?.signals ?? [])].sort((a, b) => b.composite_score - a.composite_score);

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <p className="text-muted text-sm">
          {signals.length} coins analysed
          {data?.last_scan_time ? ` · ${formatTs(data.last_scan_time)}` : ""}
        </p>
        <p className="text-xs text-muted">Buy threshold: 65 · Sell threshold: 35</p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({length: 8}).map((_, i) => (
            <div key={i} className="h-10 bg-border rounded animate-pulse" />
          ))}
        </div>
      ) : signals.length === 0 ? (
        <p className="text-muted text-sm py-10 text-center">Awaiting first scan…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left pb-3 font-medium">Symbol</th>
                <th className="text-center pb-3 font-medium">Action</th>
                <th className="text-left pb-3 font-medium">Composite</th>
                <th className="text-left pb-3 font-medium hidden md:table-cell">Technical</th>
                <th className="text-left pb-3 font-medium hidden md:table-cell">Sentiment</th>
                <th className="text-right pb-3 font-medium hidden lg:table-cell">EMA Fast</th>
                <th className="text-right pb-3 font-medium hidden lg:table-cell">EMA Slow</th>
                <th className="text-right pb-3 font-medium">RSI</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => {
                const d = s.details as Record<string, unknown>;
                return (
                  <tr key={s.symbol} className="border-b border-border/50 last:border-0 hover:bg-white/2">
                    <td className="py-3 font-semibold text-white">{s.symbol.split("/")[0]}</td>
                    <td className="py-3 text-center"><ActionBadge action={s.action} /></td>
                    <td className="py-3"><Bar value={s.composite_score} /></td>
                    <td className="py-3 hidden md:table-cell"><Bar value={s.technical_score} /></td>
                    <td className="py-3 hidden md:table-cell"><Bar value={s.sentiment_score} /></td>
                    <td className="py-3 text-right text-xs text-muted hidden lg:table-cell">
                      {d.ema_fast != null ? Number(d.ema_fast).toFixed(4) : "—"}
                    </td>
                    <td className="py-3 text-right text-xs text-muted hidden lg:table-cell">
                      {d.ema_slow != null ? Number(d.ema_slow).toFixed(4) : "—"}
                    </td>
                    <td className="py-3 text-right text-xs text-muted">
                      {d.rsi_value != null ? Number(d.rsi_value).toFixed(1) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
