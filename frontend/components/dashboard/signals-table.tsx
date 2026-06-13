"use client";

import { useSignals } from "@/hooks/use-api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatTs, cn } from "@/lib/utils";
import type { Signal } from "@/lib/api";

function ActionBadge({ action }: { action: Signal["action"] }) {
  const styles: Record<Signal["action"], string> = {
    BUY: "border-success/40 bg-success/10 text-success",
    SELL: "border-destructive/40 bg-destructive/10 text-destructive",
    HOLD: "border-border bg-muted/30 text-muted-foreground",
  };
  return (
    <Badge variant="outline" className={cn("font-semibold", styles[action])}>
      {action}
    </Badge>
  );
}

function ScoreBar({ value }: { value: number }) {
  const color =
    value >= 65 ? "bg-success" : value >= 35 ? "bg-primary" : "bg-destructive";
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span className="w-6 text-xs font-mono text-muted-foreground">
        {value.toFixed(0)}
      </span>
    </div>
  );
}

export function SignalsTable() {
  const { data, isLoading } = useSignals();
  const signals = (data?.signals ?? [])
    .slice()
    .sort((a, b) => b.composite_score - a.composite_score)
    .slice(0, 6);

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base">Top Signals</CardTitle>
          <CardDescription>From the last market scan</CardDescription>
        </div>
        {data?.last_scan_time && (
          <span className="text-xs text-muted-foreground">
            {formatTs(data.last_scan_time)}
          </span>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : signals.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Awaiting first scan…
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-border/60 hover:bg-transparent">
                <TableHead className="h-9 text-[11px] uppercase tracking-wider">Symbol</TableHead>
                <TableHead className="h-9 text-[11px] uppercase tracking-wider">Action</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Score</TableHead>
                <TableHead className="hidden h-9 text-right text-[11px] uppercase tracking-wider md:table-cell">
                  RSI
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {signals.map((s) => (
                <TableRow key={s.symbol} className="border-border/60">
                  <TableCell className="font-semibold text-foreground">
                    {s.symbol.split("/")[0]}
                  </TableCell>
                  <TableCell>
                    <ActionBadge action={s.action} />
                  </TableCell>
                  <TableCell>
                    <ScoreBar value={s.composite_score} />
                  </TableCell>
                  <TableCell className="hidden text-right text-xs text-muted-foreground md:table-cell">
                    {(s.details as Record<string, unknown>)?.rsi_value as number ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
