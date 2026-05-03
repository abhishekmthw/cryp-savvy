"use client";

import { usePortfolio } from "@/hooks/use-api";
import { Card, CardTitle } from "@/components/ui/card";
import { formatINR, formatPct } from "@/lib/utils";
import { Wallet, TrendingUp, TrendingDown, BarChart2 } from "lucide-react";

function StatCard({
  title,
  value,
  sub,
  positive,
  icon: Icon,
}: {
  title: string;
  value: string;
  sub?: string;
  positive?: boolean;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-2 text-2xl font-bold text-white">{value}</p>
          {sub && (
            <p className={`mt-1 text-xs font-medium ${positive === undefined ? "text-muted" : positive ? "text-success" : "text-danger"}`}>
              {sub}
            </p>
          )}
        </div>
        <span className="p-2 bg-accent/10 rounded-lg">
          <Icon className="w-5 h-5 text-accent" />
        </span>
      </div>
    </Card>
  );
}

export function StatCards() {
  const { data, isLoading } = usePortfolio();

  if (isLoading || !data)
    return (
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}><div className="h-20 animate-pulse bg-border rounded" /></Card>
        ))}
      </div>
    );

  const { summary, stats } = data;

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      <StatCard
        title="Balance"
        value={formatINR(summary.balance_inr)}
        sub={`${summary.open_positions} position${summary.open_positions !== 1 ? "s" : ""} open`}
        icon={Wallet}
      />
      <StatCard
        title="Portfolio Value"
        value={formatINR(summary.portfolio_value)}
        sub={`${stats.total_trades} trades total`}
        icon={BarChart2}
      />
      <StatCard
        title="Total P&L"
        value={formatINR(summary.total_pnl)}
        sub={`Win rate ${stats.win_rate.toFixed(1)}%`}
        positive={summary.total_pnl >= 0}
        icon={summary.total_pnl >= 0 ? TrendingUp : TrendingDown}
      />
      <StatCard
        title="Today's P&L"
        value={formatINR(summary.daily_pnl)}
        sub={`Avg ${formatPct(stats.avg_pnl_pct)} per trade`}
        positive={summary.daily_pnl >= 0}
        icon={summary.daily_pnl >= 0 ? TrendingUp : TrendingDown}
      />
    </div>
  );
}
