"use client";

import { useTrades } from "@/hooks/use-api";
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
import { formatUSD, formatPct, formatTs, cn } from "@/lib/utils";

export function FullTradesTable() {
  const { data, isLoading } = useTrades(200);
  const trades = data?.trades ?? [];

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>All Trades</CardTitle>
          <CardDescription>
            Most recent {trades.length} of {data?.total ?? 0} trades
          </CardDescription>
        </div>
        <Badge variant="outline" className="border-border/60 font-mono">
          {data?.total ?? 0} total
        </Badge>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : trades.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No trades yet — bot is scanning…
          </p>
        ) : (
          <ScrollArea className="w-full">
            <Table>
              <TableHeader>
                <TableRow className="border-border/60 hover:bg-transparent">
                  <TableHead className="text-[11px] uppercase tracking-wider">Time</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider">Symbol</TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider">Entry</TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider">Exit</TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider">P&amp;L</TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider">Return</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider">Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.map((t, i) => {
                  const profit = t.pnl >= 0;
                  return (
                    <TableRow key={i} className="border-border/60">
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatTs(t.ts)}
                      </TableCell>
                      <TableCell className="font-semibold text-foreground">
                        {t.symbol.split("/")[0]}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {formatUSD(t.entry_price)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatUSD(t.exit_price)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-semibold",
                          profit ? "text-success" : "text-destructive"
                        )}
                      >
                        {formatUSD(t.pnl)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right text-xs",
                          profit ? "text-success" : "text-destructive"
                        )}
                      >
                        {formatPct(t.pnl_pct)}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {t.reason}
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
