"use client";

import { useTrades } from "@/hooks/use-api";
import { Card } from "@/components/ui/card";
import { formatINR, formatPct, formatTs } from "@/lib/utils";

export function FullTradesTable() {
  const { data, isLoading } = useTrades(200);
  const trades = data?.trades ?? [];

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <p className="text-muted text-sm">{data?.total ?? 0} total trades</p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({length: 6}).map((_, i) => (
            <div key={i} className="h-10 bg-border rounded animate-pulse" />
          ))}
        </div>
      ) : trades.length === 0 ? (
        <p className="text-muted text-sm py-10 text-center">No trades yet — bot is scanning…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left pb-3 font-medium">Time</th>
                <th className="text-left pb-3 font-medium">Symbol</th>
                <th className="text-right pb-3 font-medium">Entry</th>
                <th className="text-right pb-3 font-medium">Exit</th>
                <th className="text-right pb-3 font-medium">P&L</th>
                <th className="text-right pb-3 font-medium">Return</th>
                <th className="text-left pb-3 font-medium pl-4">Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => {
                const profit = t.pnl >= 0;
                const pnlColor = profit ? "text-success" : "text-danger";
                return (
                  <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-white/2">
                    <td className="py-3 text-muted text-xs">{formatTs(t.ts)}</td>
                    <td className="py-3 font-semibold text-white">{t.symbol.split("/")[0]}</td>
                    <td className="py-3 text-right text-muted">{formatINR(t.entry_price)}</td>
                    <td className="py-3 text-right text-white">{formatINR(t.exit_price)}</td>
                    <td className={`py-3 text-right font-semibold ${pnlColor}`}>{formatINR(t.pnl)}</td>
                    <td className={`py-3 text-right text-xs ${pnlColor}`}>{formatPct(t.pnl_pct)}</td>
                    <td className="py-3 pl-4 text-xs text-muted">{t.reason}</td>
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
