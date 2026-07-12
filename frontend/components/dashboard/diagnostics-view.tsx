"use client";

import { useDiagnostics } from "@/hooks/use-api";
import type { DiagnosticsGroup } from "@/lib/api";
import { DiagnosticsExport } from "@/components/dashboard/diagnostics-export";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { formatUSD, formatPct, cn } from "@/lib/utils";

// ── small building blocks ─────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "good" | "bad";
}) {
  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardContent className="p-4">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        <p
          className={cn(
            "mt-1 text-2xl font-semibold tabular-nums",
            tone === "good" && "text-success",
            tone === "bad" && "text-destructive",
          )}
        >
          {value}
        </p>
        {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function BreakdownTable({
  rows,
  keyLabel,
  emptyNote,
}: {
  rows: DiagnosticsGroup[];
  keyLabel: string;
  emptyNote?: string;
}) {
  const meaningful = rows.filter((r) => r.key !== "unknown");
  const hasData = meaningful.length > 0;
  const display = hasData ? meaningful : rows;

  if (display.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {emptyNote ?? "No data."}
      </p>
    );
  }

  return (
    <>
      {!hasData && emptyNote && (
        <p className="mb-3 text-xs text-muted-foreground">{emptyNote}</p>
      )}
      <Table>
        <TableHeader>
          <TableRow className="border-border/60 hover:bg-transparent">
            <TableHead className="text-[11px] uppercase tracking-wider">{keyLabel}</TableHead>
            <TableHead className="text-right text-[11px] uppercase tracking-wider">Trades</TableHead>
            <TableHead className="text-right text-[11px] uppercase tracking-wider">Win&nbsp;rate</TableHead>
            <TableHead className="text-right text-[11px] uppercase tracking-wider">Avg&nbsp;P&amp;L</TableHead>
            <TableHead className="text-right text-[11px] uppercase tracking-wider">Total&nbsp;P&amp;L</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {display.map((r) => {
            const profit = r.total_pnl >= 0;
            return (
              <TableRow key={r.key} className="border-border/60">
                <TableCell className="font-medium text-foreground">{r.key}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {r.count}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.win_rate.toFixed(1)}%
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right text-xs tabular-nums",
                    r.avg_pnl_pct >= 0 ? "text-success" : "text-destructive",
                  )}
                >
                  {formatPct(r.avg_pnl_pct)}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-semibold tabular-nums",
                    profit ? "text-success" : "text-destructive",
                  )}
                >
                  {formatUSD(r.total_pnl)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </>
  );
}

// ── main view ─────────────────────────────────────────────────────────────────

export function DiagnosticsView() {
  const { data, isLoading } = useDiagnostics();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!data || data.total_trades === 0 || !data.edge) {
    return (
      <Card className="border-border/60 bg-card/70 backdrop-blur">
        <CardContent className="py-16 text-center text-sm text-muted-foreground">
          No closed trades yet — diagnostics appear once the bot has completed
          some round-trips.
        </CardContent>
      </Card>
    );
  }

  const { edge, fees, duration, coverage } = data;
  const losingEdge = edge.win_rate < edge.breakeven_win_rate;
  const profitFactorBad = edge.profit_factor < 1;

  // ── auto-generated diagnosis notes ──────────────────────────────────────────
  const notes: string[] = [];
  if (losingEdge) {
    notes.push(
      `Your realized payoff is ${edge.payoff_ratio.toFixed(2)}:1, which needs a ` +
        `${edge.breakeven_win_rate.toFixed(1)}% win rate to break even — but you're winning ` +
        `${edge.win_rate.toFixed(1)}%. The hit rate is below breakeven, so the system loses money as configured.`,
    );
  } else {
    notes.push(
      `Win rate ${edge.win_rate.toFixed(1)}% is above the ${edge.breakeven_win_rate.toFixed(1)}% ` +
        `breakeven implied by a ${edge.payoff_ratio.toFixed(2)}:1 payoff.`,
    );
  }
  if (profitFactorBad) {
    notes.push(
      `Profit factor is ${edge.profit_factor.toFixed(2)} (below 1.0): gross losses ` +
        `(${formatUSD(edge.gross_loss_usdt)}) exceed gross wins (${formatUSD(edge.gross_profit_usdt)}).`,
    );
  }
  // Winner-cutting signal: signal-reversal exits outnumbering take-profits.
  const byReason = data.by_reason ?? [];
  const tp = byReason.find((r) => r.key === "take_profit");
  const sig = byReason.find((r) => r.key === "sell_signal");
  if (sig && (!tp || sig.count > tp.count) && sig.avg_pnl < 0) {
    notes.push(
      `Most exits are signal reversals (“sell_signal”: ${sig.count} trades, avg ` +
        `${formatPct(sig.avg_pnl_pct)}) rather than hitting take-profit — winners may be ` +
        `getting cut short before reaching target.`,
    );
  }
  if (fees) {
    notes.push(
      `Fees + slippage cost an estimated ${formatUSD(fees.est_total_cost_usdt)} ` +
        `(~${fees.pct_of_gross_loss}% of gross losses) across ${data.total_trades} trades.`,
    );
  }
  if (duration && duration.avg_loss_hours > duration.avg_win_hours && duration.avg_win_hours > 0) {
    notes.push(
      `Losers are held longer than winners (${duration.avg_loss_hours}h vs ` +
        `${duration.avg_win_hours}h) — a classic “cut winners, let losers run” pattern.`,
    );
  }

  const attributed = coverage?.attributed_trades ?? 0;
  const attrNote =
    attributed === 0
      ? "Populated only for trades opened after the diagnostics instrumentation shipped — historical trades are excluded."
      : undefined;

  return (
    <div className="space-y-6">
      {/* Export toolbar — markdown report for Claude Code + file downloads */}
      <DiagnosticsExport />

      {/* Diagnosis banner */}
      <Card
        className={cn(
          "border-border/60 backdrop-blur",
          losingEdge ? "bg-destructive/10 border-destructive/40" : "bg-card/70",
        )}
      >
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Diagnosis
            <Badge
              variant="outline"
              className={cn(
                "font-mono",
                losingEdge ? "border-destructive/60 text-destructive" : "border-success/60 text-success",
              )}
            >
              {losingEdge ? "NEGATIVE EDGE" : "POSITIVE EDGE"}
            </Badge>
          </CardTitle>
          <CardDescription>
            Cause-of-loss read-out across {data.total_trades} closed trades
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            {notes.map((n, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1 text-muted-foreground">•</span>
                <span>{n}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* Edge metrics */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Win rate"
          value={`${edge.win_rate.toFixed(1)}%`}
          sub={`Breakeven ${edge.breakeven_win_rate.toFixed(1)}%`}
          tone={losingEdge ? "bad" : "good"}
        />
        <MetricCard
          label="Profit factor"
          value={edge.profit_factor.toFixed(2)}
          sub="Gross win ÷ gross loss"
          tone={profitFactorBad ? "bad" : "good"}
        />
        <MetricCard
          label="Expectancy / trade"
          value={formatUSD(edge.expectancy_usdt)}
          sub={formatPct(edge.expectancy_pct)}
          tone={edge.expectancy_usdt >= 0 ? "good" : "bad"}
        />
        <MetricCard
          label="Payoff ratio"
          value={`${edge.payoff_ratio.toFixed(2)}:1`}
          sub={`Avg win ${formatUSD(edge.avg_win_usdt)} / loss ${formatUSD(edge.avg_loss_usdt)}`}
        />
        <MetricCard
          label="Total P&L"
          value={formatUSD(edge.total_pnl_usdt)}
          tone={edge.total_pnl_usdt >= 0 ? "good" : "bad"}
        />
        <MetricCard
          label="Max drawdown"
          value={`${edge.max_drawdown_pct.toFixed(1)}%`}
          tone="bad"
        />
        <MetricCard
          label="Largest win / loss"
          value={formatUSD(edge.largest_win_usdt)}
          sub={formatUSD(edge.largest_loss_usdt)}
        />
        {fees && (
          <MetricCard
            label="Est. fee drag"
            value={formatUSD(fees.est_total_cost_usdt)}
            sub={`${fees.round_trip_pct}% round-trip · ${fees.pct_of_gross_loss}% of losses`}
            tone="bad"
          />
        )}
      </div>

      {/* Execution quality (v2 instrumentation — planned R:R, excursions, churn) */}
      {(data.rr?.coverage ?? 0) > 0 || (data.churn?.trades_per_day ?? 0) > 0 ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {data.rr && data.rr.coverage > 0 && (
            <MetricCard
              label="Planned vs realized R"
              value={`${data.rr.avg_planned_rr.toFixed(2)} → ${data.rr.avg_realized_r.toFixed(2)}R`}
              sub={`${data.rr.coverage}/${data.total_trades} instrumented · overshoot ${data.rr.stop_overshoot_pct}%`}
              tone={data.rr.avg_realized_r >= 0 ? "good" : "bad"}
            />
          )}
          {data.mae_mfe && data.mae_mfe.coverage > 0 && (
            <MetricCard
              label="Losers once ≥1% up"
              value={`${data.mae_mfe.losers_profitable_1pct.toFixed(0)}%`}
              sub={`Avg loser MFE ${data.mae_mfe.avg_mfe_losers_pct.toFixed(2)}% — clipped winners signal`}
              tone={data.mae_mfe.losers_profitable_1pct >= 25 ? "bad" : "neutral"}
            />
          )}
          {data.churn && (
            <MetricCard
              label="Churn"
              value={`${data.churn.trades_per_day.toFixed(1)}/day`}
              sub={`${data.churn.reentries_within_window} re-entries within ${data.churn.window_h}h`}
              tone={data.churn.reentries_within_window > 0 ? "bad" : "neutral"}
            />
          )}
          {data.risk && (
            <MetricCard
              label="Sharpe (daily, ann.)"
              value={data.risk.sharpe_daily_ann.toFixed(2)}
              sub={`${data.risk.daily_return_days} trading days`}
              tone={data.risk.sharpe_daily_ann >= 0 ? "good" : "bad"}
            />
          )}
        </div>
      ) : null}

      {/* Breakdowns */}
      <Card className="border-border/60 bg-card/70 backdrop-blur">
        <CardHeader>
          <CardTitle>Breakdowns</CardTitle>
          <CardDescription>
            Where the P&amp;L is coming from — biggest bleeders first
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="reason">
            <TabsList className="mb-4 flex-wrap">
              <TabsTrigger value="reason">Exit reason</TabsTrigger>
              <TabsTrigger value="symbol">Symbol</TabsTrigger>
              <TabsTrigger value="bucket">Bucket</TabsTrigger>
              <TabsTrigger value="strategy">Strategy</TabsTrigger>
              <TabsTrigger value="regime">Regime</TabsTrigger>
              <TabsTrigger value="hour">Entry hour</TabsTrigger>
            </TabsList>
            <TabsContent value="reason">
              <BreakdownTable rows={data.by_reason ?? []} keyLabel="Exit reason" />
            </TabsContent>
            <TabsContent value="symbol">
              <BreakdownTable rows={data.by_symbol ?? []} keyLabel="Symbol" />
            </TabsContent>
            <TabsContent value="bucket">
              <BreakdownTable rows={data.by_bucket ?? []} keyLabel="Bucket" emptyNote={attrNote} />
            </TabsContent>
            <TabsContent value="strategy">
              <BreakdownTable rows={data.by_strategy ?? []} keyLabel="Strategy" emptyNote={attrNote} />
            </TabsContent>
            <TabsContent value="regime">
              <BreakdownTable rows={data.by_regime ?? []} keyLabel="Regime" emptyNote={attrNote} />
            </TabsContent>
            <TabsContent value="hour">
              <BreakdownTable rows={data.by_hour ?? []} keyLabel="Hour (UTC)" />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
