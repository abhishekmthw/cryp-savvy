"use client";

import Link from "next/link";
import { ArrowDownLeft, ArrowUpRight, ArrowRight } from "lucide-react";

import { useTrades } from "@/hooks/use-api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatINR, formatPct, formatTs, cn } from "@/lib/utils";

export function TradesFeed() {
  const { data, isLoading } = useTrades(10);
  const trades = data?.trades ?? [];

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base">Recent Trades</CardTitle>
          <CardDescription>Last 10 completed</CardDescription>
        </div>
        <Link
          href="/trades"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          View all
          <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : trades.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No trades yet</p>
        ) : (
          <ScrollArea className="max-h-[320px] pr-2">
            <div className="space-y-1">
              {trades.map((t, i) => {
                const profit = t.pnl >= 0;
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg px-2 py-2 transition-colors hover:bg-accent/30"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span
                        className={cn(
                          "rounded-md p-1.5",
                          profit ? "bg-success/15" : "bg-destructive/15"
                        )}
                      >
                        {profit ? (
                          <ArrowUpRight className="h-3.5 w-3.5 text-success" />
                        ) : (
                          <ArrowDownLeft className="h-3.5 w-3.5 text-destructive" />
                        )}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-foreground">
                          {t.symbol.split("/")[0]}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {formatTs(t.ts)} · {t.reason}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p
                        className={cn(
                          "text-sm font-semibold",
                          profit ? "text-success" : "text-destructive"
                        )}
                      >
                        {formatINR(t.pnl)}
                      </p>
                      <p
                        className={cn(
                          "text-xs",
                          profit ? "text-success" : "text-destructive"
                        )}
                      >
                        {formatPct(t.pnl_pct)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
