"use client";

import { useTrades } from "@/hooks/use-api";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatINR, formatPct, formatTs } from "@/lib/utils";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

export function TradesFeed() {
  const { data, isLoading } = useTrades(10);
  const trades = data?.trades ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Recent Trades</CardTitle>
          <a href="/trades" className="text-xs text-accent hover:underline">View all</a>
        </div>
      </CardHeader>

      {isLoading ? (
        <div className="space-y-2">
          {[1,2,3].map(i => <div key={i} className="h-10 bg-border rounded animate-pulse" />)}
        </div>
      ) : trades.length === 0 ? (
        <p className="text-muted text-sm py-4 text-center">No trades yet</p>
      ) : (
        <div className="space-y-1">
          {trades.map((t, i) => {
            const profit = t.pnl >= 0;
            return (
              <div key={i} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
                <div className="flex items-center gap-3">
                  <span className={`p-1 rounded-md ${profit ? "bg-success/15" : "bg-danger/15"}`}>
                    {profit
                      ? <ArrowUpRight className="w-3.5 h-3.5 text-success" />
                      : <ArrowDownLeft className="w-3.5 h-3.5 text-danger" />}
                  </span>
                  <div>
                    <p className="text-white text-sm font-medium">{t.symbol.split("/")[0]}</p>
                    <p className="text-muted text-xs">{formatTs(t.ts)} · {t.reason}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-semibold ${profit ? "text-success" : "text-danger"}`}>
                    {formatINR(t.pnl)}
                  </p>
                  <p className={`text-xs ${profit ? "text-success" : "text-danger"}`}>
                    {formatPct(t.pnl_pct)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
