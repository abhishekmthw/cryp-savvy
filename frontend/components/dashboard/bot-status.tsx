"use client";

import { useBotStatus } from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import { formatTs } from "@/lib/utils";
import { Activity, WifiOff } from "lucide-react";

export function BotStatus() {
  const { data } = useBotStatus();
  const { connected } = useWebSocket();

  const mode    = data?.mode?.toUpperCase() ?? "—";
  const running = data?.is_running ?? false;
  const limited = data?.daily_limit_hit ?? false;
  const lastScan = data?.last_scan_time ? formatTs(data.last_scan_time) : "—";

  return (
    <div className="flex items-center gap-4 text-sm">
      {/* WebSocket badge */}
      <span className={`flex items-center gap-1.5 ${connected ? "text-success" : "text-muted"}`}>
        {connected ? <Activity className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
        <span className="hidden sm:inline">{connected ? "Live" : "Offline"}</span>
      </span>

      {/* Bot state badge */}
      <span
        className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
          limited
            ? "bg-warning/15 text-warning"
            : running
            ? "bg-success/15 text-success"
            : "bg-muted/20 text-muted"
        }`}
      >
        {limited ? "PAUSED" : running ? "RUNNING" : "STOPPED"} · {mode}
      </span>

      <span className="text-muted hidden lg:inline">Last scan: {lastScan}</span>
    </div>
  );
}
