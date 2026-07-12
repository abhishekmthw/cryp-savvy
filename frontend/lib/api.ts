/**
 * Typed API client for the Python backend.
 * All requests include the Clerk JWT in the Authorization header.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PortfolioSummary {
  balance_usdt: number;
  open_positions: number;
  portfolio_value: number;
  total_pnl: number;
  daily_pnl: number;
  total_trades: number;
}

export interface PortfolioStats {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
}

export interface Position {
  symbol: string;
  entry_price: number;
  current_price: number;
  qty: number;
  amount_usdt: number;
  stop_loss: number;
  take_profit: number;
  unrealised_pnl_pct: number;
  entry_time: number;
}

export interface Trade {
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  reason: string;
  ts: number;
}

export interface Signal {
  symbol: string;
  action: "BUY" | "SELL" | "HOLD";
  composite_score: number;
  technical_score: number;
  sentiment_score: number;
  details: Record<string, unknown>;
}

export interface BotStatus {
  is_running: boolean;
  mode: string;
  last_scan_time: number;
  open_positions: number;
  daily_limit_hit: boolean;
  daily_pnl: number;
}

export interface ChartPoint {
  ts: number;
  value: number;
}

export interface DiagnosticsEdge {
  win_rate: number;
  breakeven_win_rate: number;
  profit_factor: number;
  expectancy_usdt: number;
  expectancy_pct: number;
  avg_win_usdt: number;
  avg_loss_usdt: number;
  payoff_ratio: number;
  largest_win_usdt: number;
  largest_loss_usdt: number;
  gross_profit_usdt: number;
  gross_loss_usdt: number;
  total_pnl_usdt: number;
  max_drawdown_pct: number;
}

export interface DiagnosticsFees {
  round_trip_pct: number;
  est_total_cost_usdt: number;
  est_cost_per_trade: number;
  pct_of_gross_loss: number;
}

export interface DiagnosticsDuration {
  avg_hours: number;
  avg_win_hours: number;
  avg_loss_hours: number;
}

export interface DiagnosticsGroup {
  key: string;
  count: number;
  wins: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  avg_pnl_pct: number;
}

export interface Diagnostics {
  total_trades: number;
  edge?: DiagnosticsEdge;
  fees?: DiagnosticsFees;
  duration?: DiagnosticsDuration;
  by_reason?: DiagnosticsGroup[];
  by_symbol?: DiagnosticsGroup[];
  by_bucket?: DiagnosticsGroup[];
  by_strategy?: DiagnosticsGroup[];
  by_regime?: DiagnosticsGroup[];
  coverage?: { attributed_trades: number; unattributed_trades: number };
}

export interface ProviderStatus {
  present: boolean;
  valid: boolean;
  last4: string | null;
  verified_at: number | null;
}

export interface CredentialsSummary {
  coindcx: ProviderStatus;
  telegram: ProviderStatus;
}

export interface BucketView {
  budget: number;
  realized_pnl: number;
  deployed: number;
  available: number;
  equity: number;
  drawdown_state: "normal" | "reduced" | "halted" | "paused";
}

export interface AllocationView {
  allocated: boolean;
  total_allocated?: number;
  allocate_all?: boolean;
  status?: "active" | "paused" | "withdrawn";
  buckets?: { day: BucketView; long: BucketView };
}

export interface ClearPaperDataResponse {
  ok: boolean;
  deleted: { trades: number; positions: number; orders: number; bucket_states: number };
  was_running: boolean;
  bot_restarted: boolean;
  warning: string | null;
}

// ── Fetch helper ───────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let payload: unknown = null;
    try {
      payload = await res.json();
    } catch {
      payload = await res.text().catch(() => res.statusText);
    }
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload;
    const err = new Error(
      typeof detail === "string" ? detail : `API ${res.status}`,
    ) as Error & { status: number; detail: unknown };
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Public API calls ───────────────────────────────────────────────────────────

export const api = {
  status: (token: string) =>
    apiFetch<BotStatus>("/api/status", token),

  // Mint a short-lived, single-use ticket for the WebSocket handshake so the
  // Clerk JWT never appears in the WS URL.
  wsTicket: (token: string) =>
    apiFetch<{ ticket: string }>("/api/ws/token", token, { method: "POST" }),

  portfolio: (token: string) =>
    apiFetch<{ summary: PortfolioSummary; stats: PortfolioStats }>("/api/portfolio", token),

  portfolioHistory: (token: string) =>
    apiFetch<{ history: ChartPoint[] }>("/api/portfolio/history", token),

  diagnostics: (token: string) =>
    apiFetch<Diagnostics>("/api/portfolio/diagnostics", token),

  positions: (token: string) =>
    apiFetch<{ positions: Position[] }>("/api/positions", token),

  trades: (token: string, limit = 50) =>
    apiFetch<{ trades: Trade[]; total: number }>(`/api/trades?limit=${limit}`, token),

  signals: (token: string) =>
    apiFetch<{ signals: Signal[]; last_scan_time: number }>("/api/signals", token),

  credentials: {
    list: (token: string) =>
      apiFetch<CredentialsSummary>("/api/credentials", token),

    saveCoindcx: (token: string, body: { api_key: string; api_secret: string }) =>
      apiFetch<{ ok: boolean; verified_at: number; last4: string }>(
        "/api/credentials/coindcx",
        token,
        { method: "PUT", body: JSON.stringify(body) },
      ),

    deleteCoindcx: (token: string) =>
      apiFetch<{ ok: boolean }>("/api/credentials/coindcx", token, { method: "DELETE" }),

    testCoindcx: (token: string) =>
      apiFetch<{ ok: boolean; message: string }>(
        "/api/credentials/coindcx/test",
        token,
        { method: "POST" },
      ),

    saveTelegram: (token: string, body: { bot_token: string; chat_id: string }) =>
      apiFetch<{ ok: boolean; verified_at: number; last4: string }>(
        "/api/credentials/telegram",
        token,
        { method: "PUT", body: JSON.stringify(body) },
      ),

    deleteTelegram: (token: string) =>
      apiFetch<{ ok: boolean }>("/api/credentials/telegram", token, { method: "DELETE" }),

    testTelegram: (token: string) =>
      apiFetch<{ ok: boolean; message: string }>(
        "/api/credentials/telegram/test",
        token,
        { method: "POST" },
      ),
  },

  allocation: {
    get: (token: string) => apiFetch<AllocationView>("/api/allocation", token),
    set: (token: string, body: { total: number; day_pct: number; allocate_all: boolean }) =>
      apiFetch<{ ok: boolean; day_budget: number; long_budget: number }>(
        "/api/allocation", token, { method: "POST", body: JSON.stringify(body) },
      ),
    pause: (token: string) =>
      apiFetch<{ ok: boolean; status: string }>("/api/allocation/pause", token, { method: "POST" }),
    resume: (token: string) =>
      apiFetch<{ ok: boolean; status: string }>("/api/allocation/resume", token, { method: "POST" }),
    confirmShift: (token: string, body: { day_pct: number }) =>
      apiFetch<{ ok: boolean; day_budget: number; long_budget: number }>(
        "/api/allocation/confirm-shift", token, { method: "POST", body: JSON.stringify(body) },
      ),
  },

  bot: {
    start: (token: string) =>
      apiFetch<{ ok: boolean; is_running: boolean }>("/api/bot/start", token, {
        method: "POST",
      }),
    stop: (token: string) =>
      apiFetch<{ ok: boolean; is_running: boolean }>("/api/bot/stop", token, {
        method: "POST",
      }),
    setMode: (token: string, body: { mode: "paper" | "live"; confirm?: string }) =>
      apiFetch<{ ok: boolean; mode: string }>("/api/bot/mode", token, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    clearPaperData: (token: string) =>
      apiFetch<ClearPaperDataResponse>("/api/bot/paper-data", token, {
        method: "DELETE",
      }),
  },
};
