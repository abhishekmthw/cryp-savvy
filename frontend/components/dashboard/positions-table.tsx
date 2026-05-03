"use client";

import { usePositions } from "@/hooks/use-api";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatINR, formatPct } from "@/lib/utils";

export function PositionsTable() {
  const { data, isLoading } = usePositions();
  const positions = data?.positions ?? [];

  return (
    <Card className="h-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Open Positions</CardTitle>
          <span className="text-xs text-muted">{positions.length} / 2</span>
        </div>
      </CardHeader>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => <div key={i} className="h-12 bg-border rounded animate-pulse" />)}
        </div>
      ) : positions.length === 0 ? (
        <p className="text-muted text-sm py-6 text-center">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left pb-2 font-medium">Symbol</th>
                <th className="text-right pb-2 font-medium">Entry</th>
                <th className="text-right pb-2 font-medium">Current</th>
                <th className="text-right pb-2 font-medium">P&L</th>
                <th className="text-right pb-2 font-medium">Stop</th>
                <th className="text-right pb-2 font-medium">Target</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const pnlColor = p.unrealised_pnl_pct >= 0 ? "text-success" : "text-danger";
                return (
                  <tr key={p.symbol} className="border-b border-border/50 last:border-0">
                    <td className="py-3 font-semibold text-white">{p.symbol.split("/")[0]}</td>
                    <td className="py-3 text-right text-muted">{formatINR(p.entry_price)}</td>
                    <td className="py-3 text-right text-white">{formatINR(p.current_price)}</td>
                    <td className={`py-3 text-right font-semibold ${pnlColor}`}>
                      {formatPct(p.unrealised_pnl_pct)}
                    </td>
                    <td className="py-3 text-right text-danger text-xs">{formatINR(p.stop_loss)}</td>
                    <td className="py-3 text-right text-success text-xs">{formatINR(p.take_profit)}</td>
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
