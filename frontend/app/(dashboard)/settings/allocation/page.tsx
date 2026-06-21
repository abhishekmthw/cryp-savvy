"use client";

import { useMemo, useState } from "react";
import { Loader2, Wallet, PauseCircle, PlayCircle, ShieldAlert } from "lucide-react";

import { useAllocation, usePauseAllocation, useSetAllocation } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { formatUSD, formatPct, cn } from "@/lib/utils";
import type { BucketView } from "@/lib/api";

const DD_COLOR: Record<string, string> = {
  normal: "bg-emerald-500/15 text-emerald-500",
  reduced: "bg-amber-500/15 text-amber-500",
  halted: "bg-orange-500/15 text-orange-500",
  paused: "bg-destructive/15 text-destructive",
};

function BucketCard({ name, b }: { name: string; b: BucketView }) {
  const pnlPos = b.realized_pnl >= 0;
  return (
    <Card className="border-border/60 bg-card/60 backdrop-blur">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm capitalize">{name}-trading bucket</CardTitle>
          <Badge className={cn("text-[10px] uppercase", DD_COLOR[b.drawdown_state] ?? "")}>
            {b.drawdown_state}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-sm">
        <Stat label="Budget" value={formatUSD(b.budget)} />
        <Stat label="Equity" value={formatUSD(b.equity)} />
        <Stat label="Deployed" value={formatUSD(b.deployed)} />
        <Stat label="Available" value={formatUSD(b.available)} />
        <Stat
          label="Realized P&L"
          value={formatUSD(b.realized_pnl)}
          className={pnlPos ? "text-emerald-500" : "text-destructive"}
        />
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("font-semibold tabular-nums", className)}>{value}</p>
    </div>
  );
}

export default function AllocationPage() {
  const { data, isLoading } = useAllocation();
  const setAlloc = useSetAllocation();
  const pause = usePauseAllocation();

  const [total, setTotal] = useState("");
  const [dayPct, setDayPct] = useState(30);

  const totalNum = parseFloat(total) || 0;
  const dayBudget = useMemo(() => (totalNum * dayPct) / 100, [totalNum, dayPct]);
  const longBudget = totalNum - dayBudget;
  const valid = totalNum > 0;

  function save() {
    if (!valid) return;
    setAlloc.mutate({ total: totalNum, day_pct: dayPct, allocate_all: false });
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-1">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Wallet className="h-6 w-6 text-primary" /> Capital allocation
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Decide how much USDT the bot may trade and how it splits between fast
          day-trades and longer-term holds.{" "}
          <span className="text-foreground">
            The bot never withdraws profit — gains compound inside each bucket
            until you stop it.
          </span>
        </p>
      </div>

      {/* Current allocation */}
      {!isLoading && data?.allocated && data.buckets && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Allocated <span className="font-semibold text-foreground">
                {formatUSD(data.total_allocated ?? 0)}
              </span>{" "}
              · status{" "}
              <span className="font-semibold capitalize text-foreground">{data.status}</span>
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => pause.mutate(data.status === "paused")}
              disabled={pause.isPending}
            >
              {data.status === "paused" ? (
                <><PlayCircle className="mr-1.5 h-4 w-4" /> Resume</>
              ) : (
                <><PauseCircle className="mr-1.5 h-4 w-4" /> Pause</>
              )}
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <BucketCard name="day" b={data.buckets.day} />
            <BucketCard name="long" b={data.buckets.long} />
          </div>
        </div>
      )}

      {/* Set / update allocation */}
      <Card className="border-border/60 bg-card/60 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-base">
            {data?.allocated ? "Update allocation" : "Allocate capital"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="total">Total USDT for the bot</Label>
            <Input
              id="total"
              type="number"
              inputMode="decimal"
              min={0}
              placeholder="e.g. 1000"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <Label>Split</Label>
              <span className="text-muted-foreground">
                {dayPct}% day · {100 - dayPct}% long
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={dayPct}
              onChange={(e) => setDayPct(parseInt(e.target.value, 10))}
              className="w-full accent-primary"
            />
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg border border-border/60 bg-background/50 p-3">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Day bucket
                </p>
                <p className="font-semibold tabular-nums">{formatUSD(dayBudget)}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-background/50 p-3">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Long bucket
                </p>
                <p className="font-semibold tabular-nums">{formatUSD(longBudget)}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-muted-foreground">
            <ShieldAlert className="h-4 w-4 shrink-0 text-amber-500" />
            Allocating in live mode commits real USDT. Validate in paper mode and
            review the backtest report before going live.
          </div>

          <Button
            onClick={save}
            disabled={!valid || setAlloc.isPending}
            className="bg-gradient-to-r from-primary to-fuchsia-600 text-white"
          >
            {setAlloc.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {data?.allocated ? "Update allocation" : "Allocate"}
          </Button>

          {setAlloc.error && (
            <p className="text-xs text-destructive">
              {(setAlloc.error as Error).message ?? "Failed to save allocation"}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
