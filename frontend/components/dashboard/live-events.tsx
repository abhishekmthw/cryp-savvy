"use client";

import { Zap, TrendingUp, TrendingDown, AlertTriangle, RefreshCw } from "lucide-react";

import { useWebSocket } from "@/hooks/use-websocket";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { WsEvent } from "@/lib/ws";
import { formatTs, cn } from "@/lib/utils";

interface EventConfig {
  icon: React.ElementType;
  color: string;
  bg: string;
  label: string;
}

const config: Record<string, EventConfig> = {
  trade_buy: {
    icon: TrendingUp,
    color: "text-success",
    bg: "bg-success/10",
    label: "BUY",
  },
  trade_sell: {
    icon: TrendingDown,
    color: "text-destructive",
    bg: "bg-destructive/10",
    label: "SELL",
  },
  scan_complete: {
    icon: RefreshCw,
    color: "text-primary",
    bg: "bg-primary/10",
    label: "SCAN",
  },
  daily_limit_hit: {
    icon: AlertTriangle,
    color: "text-warning",
    bg: "bg-warning/10",
    label: "PAUSED",
  },
  snapshot: {
    icon: Zap,
    color: "text-muted-foreground",
    bg: "bg-muted/30",
    label: "CONNECTED",
  },
};

function EventRow({ event }: { event: WsEvent }) {
  const ts = (event.data.timestamp as number) ?? Date.now() / 1000;
  const c = config[event.type] ?? config.snapshot;
  const { icon: Icon, color, bg, label } = c;

  let detail = "";
  if (event.type === "trade_buy") {
    detail = `${event.data.symbol} @ ₹${Number(event.data.price).toLocaleString("en-IN")}`;
  } else if (event.type === "trade_sell") {
    detail = `${event.data.symbol} · ${
      Number(event.data.pnl_pct) >= 0 ? "+" : ""
    }${Number(event.data.pnl_pct).toFixed(2)}%`;
  } else if (event.type === "scan_complete") {
    detail = `${event.data.open_positions} position${
      Number(event.data.open_positions) !== 1 ? "s" : ""
    } open`;
  }

  return (
    <div className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-accent/30">
      <span className={cn("rounded-md p-1.5", bg)}>
        <Icon className={cn("h-3.5 w-3.5", color)} />
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm font-semibold", color)}>{label}</p>
        {detail && (
          <p className="truncate text-xs text-muted-foreground">{detail}</p>
        )}
      </div>
      <span className="shrink-0 text-xs text-muted-foreground">{formatTs(ts)}</span>
    </div>
  );
}

export function LiveEvents() {
  const { events, connected } = useWebSocket();

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base">Live Events</CardTitle>
          <CardDescription>Streamed over WebSocket</CardDescription>
        </div>
        <Badge
          variant="outline"
          className={cn(
            "font-mono text-[10px]",
            connected
              ? "border-success/40 bg-success/10 text-success"
              : "border-border bg-muted/30 text-muted-foreground"
          )}
        >
          {connected ? "● LIVE" : "○ OFFLINE"}
        </Badge>
      </CardHeader>
      <CardContent className="pt-0">
        {events.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Waiting for events…
          </p>
        ) : (
          <ScrollArea className="max-h-[320px] pr-2">
            <div className="space-y-1">
              {events.map((e, i) => (
                <EventRow key={i} event={e} />
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
