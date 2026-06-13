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
import { formatINR, formatPct, cn } from "@/lib/utils";

export function PositionsTable() {
  const { data, isLoading } = usePositions();
  const positions = data?.positions ?? [];

  return (
    <Card className="h-full border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="text-base">Open Positions</CardTitle>
          <CardDescription>Live unrealised P&amp;L</CardDescription>
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
                <TableHead className="h-9 text-[11px] uppercase tracking-wider">Symbol</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Entry</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Current</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">P&amp;L</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Stop</TableHead>
                <TableHead className="h-9 text-right text-[11px] uppercase tracking-wider">Target</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((p) => {
                const profit = p.unrealised_pnl_pct >= 0;
                return (
                  <TableRow key={p.symbol} className="border-border/60">
                    <TableCell className="font-semibold text-foreground">
                      {p.symbol.split("/")[0]}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatINR(p.entry_price)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatINR(p.current_price)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right font-semibold",
                        profit ? "text-success" : "text-destructive"
                      )}
                    >
                      {formatPct(p.unrealised_pnl_pct)}
                    </TableCell>
                    <TableCell className="text-right text-xs text-destructive/80">
                      {formatINR(p.stop_loss)}
                    </TableCell>
                    <TableCell className="text-right text-xs text-success/80">
                      {formatINR(p.take_profit)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
