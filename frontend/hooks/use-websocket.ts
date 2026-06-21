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
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, BotStatus, Position, PortfolioStats, PortfolioSummary } from "@/lib/api";
import { createWebSocket, WsEvent } from "@/lib/ws";

/** Patch live prices into the cache in place — no refetch. */
function patchPrices(qc: QueryClient, event: WsEvent) {
  const prices = (event.data.prices ?? {}) as Record<string, number>;
  const portfolioValue = event.data.portfolio_value as number | undefined;
  const dailyPnl = event.data.daily_pnl as number | undefined;

  qc.setQueryData<{ positions: Position[] }>(["positions"], (old) => {
    if (!old?.positions) return old;
    return {
      positions: old.positions.map((p) => {
        const np = prices[p.symbol];
        if (np == null) return p;
        const upnl = p.entry_price ? ((np - p.entry_price) / p.entry_price) * 100 : 0;
        return { ...p, current_price: np, unrealised_pnl_pct: Math.round(upnl * 100) / 100 };
      }),
    };
  });

  if (portfolioValue != null || dailyPnl != null) {
    qc.setQueryData<{ summary: PortfolioSummary; stats: PortfolioStats }>(
      ["portfolio"],
      (old) => {
        if (!old?.summary) return old;
        return {
          ...old,
          summary: {
            ...old.summary,
            ...(portfolioValue != null ? { portfolio_value: portfolioValue } : {}),
            ...(dailyPnl != null ? { daily_pnl: dailyPnl } : {}),
          },
        };
      },
    );
  }

  if (dailyPnl != null) {
    qc.setQueryData<BotStatus>(["status"], (old) =>
      old ? { ...old, daily_pnl: dailyPnl } : old,
    );
  }
}

export function useWebSocket() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    // Fetch a fresh single-use WS ticket before each (re)connect.
    const getTicket = async (): Promise<string | null> => {
      try {
        const token = await getToken();
        if (!token) return null;
        const { ticket } = await api.wsTicket(token);
        return ticket;
      } catch {
        return null;
      }
    };

    cleanupRef.current = createWebSocket(
      getTicket,
      (event) => {
        // High-frequency live prices: patch the cache in place (no refetch) so
        // positions/portfolio update instantly, like an exchange ticker.
        if (event.type === "price_update") {
          patchPrices(queryClient, event);
          return; // don't spam the event log with price ticks
        }

        // Append to event log (cap at 50)
        setEvents((prev) => [event, ...prev].slice(0, 50));

        // Invalidate queries on actionable (discrete) events
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

    return () => {
      cleanupRef.current?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally runs once on mount

  return { events, connected };
}
