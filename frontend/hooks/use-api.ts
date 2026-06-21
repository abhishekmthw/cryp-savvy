"use client";

/**
 * React Query hooks for all backend API endpoints.
 * Each hook fetches a Clerk token and passes it to the typed API client.
 */

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const REFETCH_INTERVAL = 15_000; // 15 s fallback polling (WebSocket price_update is the primary path)

function useToken() {
  const { getToken } = useAuth();
  return getToken;
}

export function useBotStatus() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["status"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.status(token);
    },
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function usePortfolio() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["portfolio"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.portfolio(token);
    },
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function usePortfolioHistory() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["portfolioHistory"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.portfolioHistory(token);
    },
    refetchInterval: 60_000, // chart doesn't need to update as often
  });
}

export function usePositions() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["positions"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.positions(token);
    },
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useTrades(limit = 50) {
  const getToken = useToken();
  return useQuery({
    queryKey: ["trades", limit],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.trades(token, limit);
    },
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useSignals() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["signals"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.signals(token);
    },
    refetchInterval: REFETCH_INTERVAL,
  });
}

// ── Capital allocation ────────────────────────────────────────────────────────

export function useAllocation() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["allocation"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.allocation.get(token);
    },
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useSetAllocation() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { total: number; day_pct: number; allocate_all: boolean }) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.allocation.set(token, body);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["allocation"] }),
  });
}

export function usePauseAllocation() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (resume: boolean) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return resume ? api.allocation.resume(token) : api.allocation.pause(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["allocation"] }),
  });
}

// ── Credentials ──────────────────────────────────────────────────────────────

export function useCredentials() {
  const getToken = useToken();
  return useQuery({
    queryKey: ["credentials"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.list(token);
    },
    staleTime: 0,
  });
}

export function useSaveCoindcx() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { api_key: string; api_secret: string }) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.saveCoindcx(token, body);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });
}

export function useDeleteCoindcx() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.deleteCoindcx(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });
}

export function useTestCoindcx() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.testCoindcx(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });
}

export function useSaveTelegram() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { bot_token: string; chat_id: string }) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.saveTelegram(token, body);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });
}

export function useDeleteTelegram() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.deleteTelegram(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });
}

export function useTestTelegram() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.credentials.testTelegram(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });
}

// ── Bot control ─────────────────────────────────────────────────────────────

export function useStartBot() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.bot.start(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status"] }),
  });
}

export function useStopBot() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.bot.stop(token);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status"] }),
  });
}

export function useSetMode() {
  const getToken = useToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { mode: "paper" | "live"; confirm?: string }) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return api.bot.setMode(token, body);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status"] }),
  });
}
