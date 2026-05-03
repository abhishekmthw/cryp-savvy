"use client";

import { useWebSocket } from "@/hooks/use-websocket";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { WsEvent } from "@/lib/ws";
import { formatTs } from "@/lib/utils";
import { Zap, TrendingUp, TrendingDown, AlertTriangle, RefreshCw } from "lucide-react";

function EventRow({ event }: { event: WsEvent }) {
  const ts = (event.data.timestamp as number) ?? Date.now() / 1000;

  const config: Record<string, { icon: React.ElementType; color: string; label: string }> = {
    trade_buy:       { icon: TrendingUp,    color: "text-success", label: "BUY" },
    trade_sell:      { icon: TrendingDown,  color: "text-danger",  label: "SELL" },
    scan_complete:   { icon: RefreshCw,     color: "text-accent",  label: "SCAN" },
    daily_limit_hit: { icon: AlertTriangle, color: "text-warning", label: "PAUSED" },
    snapshot:        { icon: Zap,           color: "text-muted",   label: "CONNECTED" },
  };

  const { icon: Icon, color, label } = config[event.type] ?? config.snapshot;

  let detail = "";
  if (event.type === "trade_buy")
    detail = `${event.data.symbol} @ ₹${Number(event.data.price).toLocaleString("en-IN")}`;
  else if (event.type === "trade_sell")
    detail = `${event.data.symbol} · ${Number(event.data.pnl_pct) >= 0 ? "+" : ""}${Number(event.data.pnl_pct).toFixed(2)}%`;
  else if (event.type === "scan_complete")
    detail = `${event.data.open_positions} position${Number(event.data.open_positions) !== 1 ? "s" : ""} open`;

  return (
    <div className="flex items-center gap-3 py-2 border-b border-border/50 last:border-0">
      <span className={`p-1 rounded-md bg-white/5`}>
        <Icon className={`w-3.5 h-3.5 ${color}`} />
      </span>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-semibold ${color}`}>{label}</p>
        {detail && <p className="text-xs text-muted truncate">{detail}</p>}
      </div>
      <span className="text-xs text-muted shrink-0">{formatTs(ts)}</span>
    </div>
  );
}

export function LiveEvents() {
  const { events } = useWebSocket();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Live Events</CardTitle>
      </CardHeader>

      {events.length === 0 ? (
        <p className="text-muted text-sm py-4 text-center">
          Waiting for events…
        </p>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          {events.map((e, i) => <EventRow key={i} event={e} />)}
        </div>
      )}
    </Card>
  );
}
