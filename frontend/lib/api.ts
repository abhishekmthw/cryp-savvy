/**
 * Typed API client for the Python backend.
 * All requests include the Clerk JWT in the Authorization header.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PortfolioSummary {
  balance_inr: number;
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
  amount_inr: number;
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

// ── Fetch helper ───────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Public API calls ───────────────────────────────────────────────────────────

export const api = {
  status: (token: string) =>
    apiFetch<BotStatus>("/api/status", token),

  portfolio: (token: string) =>
    apiFetch<{ summary: PortfolioSummary; stats: PortfolioStats }>("/api/portfolio", token),

  portfolioHistory: (token: string) =>
    apiFetch<{ history: ChartPoint[] }>("/api/portfolio/history", token),

  positions: (token: string) =>
    apiFetch<{ positions: Position[] }>("/api/positions", token),

  trades: (token: string, limit = 50) =>
    apiFetch<{ trades: Trade[]; total: number }>(`/api/trades?limit=${limit}`, token),

  signals: (token: string) =>
    apiFetch<{ signals: Signal[]; last_scan_time: number }>("/api/signals", token),
};
