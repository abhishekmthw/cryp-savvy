"use client";

import { Activity, WifiOff } from "lucide-react";

import { useBotStatus } from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import { formatTs } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function BotStatus() {
  const { data } = useBotStatus();
  const { connected } = useWebSocket();

  const mode = data?.mode?.toUpperCase() ?? "—";
  const running = data?.is_running ?? false;
  const limited = data?.daily_limit_hit ?? false;
  const lastScan = data?.last_scan_time ? formatTs(data.last_scan_time) : "—";

  return (
    <div className="flex items-center gap-2 text-xs md:gap-3">
      <span
        className={cn(
          "flex items-center gap-1.5 rounded-full border px-2 py-1 transition-colors",
          connected
            ? "border-success/40 bg-success/10 text-success"
            : "border-border bg-muted/30 text-muted-foreground"
        )}
      >
        <span className="relative flex h-1.5 w-1.5">
          {connected && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
          )}
          <span
            className={cn(
              "relative inline-flex h-1.5 w-1.5 rounded-full",
              connected ? "bg-success" : "bg-muted-foreground"
            )}
          />
        </span>
        {connected ? (
          <>
            <Activity className="h-3 w-3" />
            <span className="hidden sm:inline">Live</span>
          </>
        ) : (
          <>
            <WifiOff className="h-3 w-3" />
            <span className="hidden sm:inline">Offline</span>
          </>
        )}
      </span>

      <Badge
        variant="outline"
        className={cn(
          "font-semibold uppercase tracking-wide",
          limited
            ? "border-warning/40 bg-warning/10 text-warning"
            : running
            ? "border-success/40 bg-success/10 text-success"
            : "border-border bg-muted/30 text-muted-foreground"
        )}
      >
        {limited ? "Paused" : running ? "Running" : "Stopped"} · {mode}
      </Badge>

      <span className="hidden text-muted-foreground lg:inline">
        Last scan {lastScan}
      </span>
    </div>
  );
}
