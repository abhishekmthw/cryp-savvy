"use client";

import { usePositions } from "@/hooks/use-api";
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
import { Badge } from "@/components/ui/badge";
import { formatINR, formatPct, formatQty, cn } from "@/lib/utils";

export function PositionsTable() {
  const { data, isLoading } = usePositions();
  const positions = data?.positions ?? [];

  const totals = positions.reduce(
    (acc, p) => {
      const value = p.qty * p.current_price;
      acc.invested += p.amount_inr;
      acc.value += value;
      return acc;
    },
    { invested: 0, value: 0 },
  );
  const totalPnlPct =
    totals.invested > 0 ? ((totals.value - totals.invested) / totals.invested) * 100 : 0;
  const totalProfit = totalPnlPct >= 0;

  return (
    <Card className="h-full border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="text-base">Open Positions</CardTitle>
          <CardDescription>Live allocation &amp; unrealised P&amp;L</CardDescription>
        </div>
        <Badge variant="outline" className="border-border/60 font-mono">
          {positions.length} / 2
        </Badge>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : positions.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <div className="rounded-full border border-dashed border-border/60 p-3">
              <span className="block h-2 w-2 rounded-full bg-muted-foreground/40" />
            </div>
            <p className="text-sm text-muted-foreground">No open positions</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-border/60 hover:bg-transparent">
                <TableHead className="h-9 text-[11px] uppercase tracking-wider">Coin</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Qty</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Buy</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Price</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Invested</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Value</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Change</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((p) => {
                const profit = p.unrealised_pnl_pct >= 0;
                const currentValue = p.qty * p.current_price;
                return (
                  <TableRow key={p.symbol} className="border-border/60">
                    <TableCell className="font-semibold text-foreground">
                      <div>{p.symbol.split("/")[0]}</div>
                      <div className="mt-0.5 text-[10px] font-normal text-muted-foreground">
                        SL {formatINR(p.stop_loss)} · TP {formatINR(p.take_profit)}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-foreground/90">
                      {formatQty(p.qty)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatINR(p.entry_price)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatINR(p.current_price)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatINR(p.amount_inr)}
                    </TableCell>
                    <TableCell className="text-right font-semibold text-foreground">
                      {formatINR(currentValue)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right font-semibold",
                        profit ? "text-success" : "text-destructive",
                      )}
                    >
                      {formatPct(p.unrealised_pnl_pct)}
                    </TableCell>
                  </TableRow>
                );
              })}
              <TableRow className="border-border/60 bg-muted/20 hover:bg-muted/20">
                <TableCell className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Total
                </TableCell>
                <TableCell />
                <TableCell />
                <TableCell />
                <TableCell className="text-right text-xs font-semibold text-foreground">
                  {formatINR(totals.invested)}
                </TableCell>
                <TableCell className="text-right text-xs font-semibold text-foreground">
                  {formatINR(totals.value)}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right text-xs font-bold",
                    totalProfit ? "text-success" : "text-destructive",
                  )}
                >
                  {formatPct(totalPnlPct)}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
