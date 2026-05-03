"use client";

/**
 * React Query hooks for all backend API endpoints.
 * Each hook fetches a Clerk token and passes it to the typed API client.
 */

import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const REFETCH_INTERVAL = 30_000; // 30 s fallback polling (WebSocket is the primary path)

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
