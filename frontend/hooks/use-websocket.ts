"use client";

/**
 * WebSocket hook.
 * Establishes a connection, handles reconnection, and returns:
 *   - `events`: last 50 real-time events from the bot
 *   - `connected`: current connection state
 *
 * On trade_buy / trade_sell events it automatically invalidates the
 * portfolio, positions, and trades queries so the UI refreshes.
 */

import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createWebSocket, WsEvent } from "@/lib/ws";

export function useWebSocket() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let active = true;

    getToken().then((token) => {
      if (!token || !active) return;

      cleanupRef.current = createWebSocket(
        token,
        (event) => {
          // Append to event log (cap at 50)
          setEvents((prev) => [event, ...prev].slice(0, 50));

          // Invalidate queries on actionable events
          if (event.type === "trade_buy" || event.type === "trade_sell") {
            queryClient.invalidateQueries({ queryKey: ["portfolio"] });
            queryClient.invalidateQueries({ queryKey: ["positions"] });
            queryClient.invalidateQueries({ queryKey: ["trades"] });
            queryClient.invalidateQueries({ queryKey: ["portfolioHistory"] });
          }
          if (event.type === "scan_complete") {
            queryClient.invalidateQueries({ queryKey: ["signals"] });
            queryClient.invalidateQueries({ queryKey: ["status"] });
          }
        },
        setConnected
      );
    });

    return () => {
      active = false;
      cleanupRef.current?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally runs once on mount

  return { events, connected };
}
