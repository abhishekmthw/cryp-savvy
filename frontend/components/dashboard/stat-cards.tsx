"use client";

import { Wallet, TrendingUp, TrendingDown, BarChart2 } from "lucide-react";

import { usePortfolio } from "@/hooks/use-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatUSD, formatPct, cn } from "@/lib/utils";

interface StatProps {
  title: string;
  value: string;
  sub?: string;
  positive?: boolean;
  icon: React.ElementType;
  accent?: "primary" | "success" | "danger";
}

function StatCard({ title, value, sub, positive, icon: Icon, accent = "primary" }: StatProps) {
  const accentClass =
    accent === "success"
      ? "from-success/15 to-transparent text-success"
      : accent === "danger"
      ? "from-destructive/15 to-transparent text-destructive"
      : "from-primary/15 to-transparent text-primary";

  return (
    <Card className="group relative overflow-hidden border-border/60 bg-card/70 backdrop-blur transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5">
      <div
        className={cn(
          "pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-gradient-radial blur-2xl transition-opacity",
          "bg-gradient-to-br opacity-60 group-hover:opacity-90",
          accentClass
        )}
      />
      <CardContent className="relative flex items-start justify-between p-5">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">{value}</p>
          {sub && (
            <p
              className={cn(
                "mt-1 text-xs font-medium",
                positive === undefined
                  ? "text-muted-foreground"
                  : positive
                  ? "text-success"
                  : "text-destructive"
              )}
            >
              {sub}
            </p>
          )}
        </div>
        <span
          className={cn(
            "rounded-xl border border-border/60 bg-background/60 p-2.5 shadow-sm transition-transform group-hover:scale-110",
            accent === "success"
              ? "text-success"
              : accent === "danger"
              ? "text-destructive"
              : "text-primary"
          )}
        >
          <Icon className="h-5 w-5" />
        </span>
      </CardContent>
    </Card>
  );
}

export function StatCards() {
  const { data, isLoading } = usePortfolio();

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="border-border/60 bg-card/70">
            <CardContent className="p-5">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="mt-3 h-7 w-32" />
              <Skeleton className="mt-2 h-3 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const { summary, stats } = data;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        title="Balance"
        value={formatUSD(summary.balance_usdt)}
        sub={`${summary.open_positions} position${summary.open_positions !== 1 ? "s" : ""} open`}
        icon={Wallet}
      />
      <StatCard
        title="Portfolio Value"
        value={formatUSD(summary.portfolio_value)}
        sub={`${stats.total_trades} trades total`}
        icon={BarChart2}
      />
      <StatCard
        title="Total P&L"
        value={formatUSD(summary.total_pnl)}
        sub={`Win rate ${stats.win_rate.toFixed(1)}%`}
        positive={summary.total_pnl >= 0}
        icon={summary.total_pnl >= 0 ? TrendingUp : TrendingDown}
        accent={summary.total_pnl >= 0 ? "success" : "danger"}
      />
      <StatCard
        title="Today's P&L"
        value={formatUSD(summary.daily_pnl)}
        sub={`Avg ${formatPct(stats.avg_pnl_pct)} per trade`}
        positive={summary.daily_pnl >= 0}
        icon={summary.daily_pnl >= 0 ? TrendingUp : TrendingDown}
        accent={summary.daily_pnl >= 0 ? "success" : "danger"}
      />
    </div>
  );
}
