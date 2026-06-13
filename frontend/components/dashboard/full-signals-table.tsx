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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
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

function Bar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  const color =
    pct >= 65 ? "bg-success" : pct >= 35 ? "bg-primary" : "bg-destructive";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-muted-foreground">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

export function FullSignalsTable() {
  const { data, isLoading } = useSignals();
  const signals = [...(data?.signals ?? [])].sort(
    (a, b) => b.composite_score - a.composite_score
  );

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>Signal Scanner</CardTitle>
          <CardDescription>
            {signals.length} coins analysed
            {data?.last_scan_time ? ` · ${formatTs(data.last_scan_time)}` : ""}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="border-success/40 bg-success/10 text-success">
            Buy ≥ 65
          </Badge>
          <Badge variant="outline" className="border-destructive/40 bg-destructive/10 text-destructive">
            Sell ≤ 35
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : signals.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Awaiting first scan…
          </p>
        ) : (
          <ScrollArea className="w-full">
            <Table>
              <TableHeader>
                <TableRow className="border-border/60 hover:bg-transparent">
                  <TableHead className="text-[11px] uppercase tracking-wider">Symbol</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider">Action</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider">Composite</TableHead>
                  <TableHead className="hidden text-[11px] uppercase tracking-wider md:table-cell">
                    Technical
                  </TableHead>
                  <TableHead className="hidden text-[11px] uppercase tracking-wider md:table-cell">
                    Sentiment
                  </TableHead>
                  <TableHead className="hidden text-right text-[11px] uppercase tracking-wider lg:table-cell">
                    EMA Fast
                  </TableHead>
                  <TableHead className="hidden text-right text-[11px] uppercase tracking-wider lg:table-cell">
                    EMA Slow
                  </TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider">
                    RSI
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.map((s) => {
                  const d = s.details as Record<string, unknown>;
                  return (
                    <TableRow key={s.symbol} className="border-border/60">
                      <TableCell className="font-semibold text-foreground">
                        {s.symbol.split("/")[0]}
                      </TableCell>
                      <TableCell>
                        <ActionBadge action={s.action} />
                      </TableCell>
                      <TableCell>
                        <Bar value={s.composite_score} />
                      </TableCell>
                      <TableCell className="hidden md:table-cell">
                        <Bar value={s.technical_score} />
                      </TableCell>
                      <TableCell className="hidden md:table-cell">
                        <Bar value={s.sentiment_score} />
                      </TableCell>
                      <TableCell className="hidden text-right text-xs text-muted-foreground lg:table-cell">
                        {d.ema_fast != null ? Number(d.ema_fast).toFixed(4) : "—"}
                      </TableCell>
                      <TableCell className="hidden text-right text-xs text-muted-foreground lg:table-cell">
                        {d.ema_slow != null ? Number(d.ema_slow).toFixed(4) : "—"}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {d.rsi_value != null ? Number(d.rsi_value).toFixed(1) : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
