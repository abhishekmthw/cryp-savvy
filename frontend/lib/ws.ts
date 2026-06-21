/**
 * WebSocket client with automatic reconnection.
 *
 * Auth uses a single-use handshake *ticket* (minted via POST /api/ws/token),
 * NOT the Clerk JWT — the JWT must never appear in a URL. A fresh ticket is
 * fetched before every (re)connect because tickets are consumed on use.
 */

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export type WsEventType =
  | "snapshot"
  | "scan_complete"
  | "trade_buy"
  | "trade_sell"
  | "daily_limit_hit"
  | "price_update"
  | "shift_suggestion"
  | "bucket_drawdown"
  | "ping";

export interface WsEvent {
  type: WsEventType;
  data: Record<string, unknown>;
}

export function createWebSocket(
  getTicket: () => Promise<string | null>,
  onMessage: (event: WsEvent) => void,
  onStatusChange?: (connected: boolean) => void
): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  let retryDelay = 2000;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  async function connect() {
    if (stopped) return;
    const ticket = await getTicket();
    if (stopped || !ticket) {
      scheduleReconnect();
      return;
    }

    ws = new WebSocket(`${WS_URL}/ws?ticket=${encodeURIComponent(ticket)}`);

    ws.onopen = () => {
      retryDelay = 2000;
      onStatusChange?.(true);
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WsEvent;
        if (event.type === "ping") return; // heartbeat — ignore
        onMessage(event);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      onStatusChange?.(false);
      scheduleReconnect();
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  function scheduleReconnect() {
    if (stopped || retryTimer) return;
    const wait = retryDelay;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      connect();
    }, wait);
    // Exponential back-off with jitter, capped at 15s, so a server restart
    // doesn't cause a synchronized thundering herd of reconnects.
    retryDelay = Math.min(retryDelay * 1.5 + Math.random() * 1000, 15_000);
  }

  // Reconnect promptly when the tab regains focus.
  const onVisible = () => {
    if (!stopped && document.visibilityState === "visible" &&
        (!ws || ws.readyState === WebSocket.CLOSED)) {
      retryDelay = 2000;
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      connect();
    }
  };
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisible);
  }

  connect();

  // Return a cleanup function
  return () => {
    stopped = true;
    if (retryTimer) clearTimeout(retryTimer);
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisible);
    }
    ws?.close();
  };
}
