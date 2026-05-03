/**
 * WebSocket client with automatic reconnection.
 * Tokens are passed as a query parameter because browsers cannot set
 * custom headers on WebSocket upgrades.
 */

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export type WsEventType =
  | "snapshot"
  | "scan_complete"
  | "trade_buy"
  | "trade_sell"
  | "daily_limit_hit";

export interface WsEvent {
  type: WsEventType;
  data: Record<string, unknown>;
}

export function createWebSocket(
  token: string,
  onMessage: (event: WsEvent) => void,
  onStatusChange?: (connected: boolean) => void
): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  let retryDelay = 2000;

  function connect() {
    if (stopped) return;

    ws = new WebSocket(`${WS_URL}/ws?token=${encodeURIComponent(token)}`);

    ws.onopen = () => {
      retryDelay = 2000;
      onStatusChange?.(true);
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WsEvent;
        onMessage(event);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      onStatusChange?.(false);
      if (!stopped) {
        // Exponential back-off, cap at 30 seconds
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 30_000);
      }
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  connect();

  // Return a cleanup function
  return () => {
    stopped = true;
    ws?.close();
  };
}
