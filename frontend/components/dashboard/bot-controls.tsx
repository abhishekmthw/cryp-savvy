"use client";

import { Loader2, Play, Square } from "lucide-react";
import { useBotStatus, useSetMode, useStartBot, useStopBot } from "@/hooks/use-api";

export function BotControls() {
  const { data } = useBotStatus();
  const start = useStartBot();
  const stop  = useStopBot();
  const setMode = useSetMode();

  const running = data?.is_running ?? false;
  const mode    = (data?.mode ?? "paper") as "paper" | "live";

  function toggleMode(next: "paper" | "live") {
    if (next === mode) return;
    if (next === "live") {
      const ok = confirm(
        "Switch to LIVE trading? Your real CoinDCX balance will be used for trades.",
      );
      if (!ok) return;
      setMode.mutate({ mode: "live", confirm: "I_ACCEPT_LIVE_RISK" });
    } else {
      setMode.mutate({ mode: "paper" });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 mb-6">
      {running ? (
        <button
          onClick={() => stop.mutate()}
          disabled={stop.isPending}
          className="px-4 py-2 rounded-lg bg-rose-500/15 text-rose-300 border border-rose-500/40 text-sm font-medium hover:bg-rose-500/25 inline-flex items-center gap-2 disabled:opacity-50"
        >
          {stop.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
          Stop bot
        </button>
      ) : (
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending}
          className="px-4 py-2 rounded-lg bg-accent text-black text-sm font-medium hover:bg-accent/90 inline-flex items-center gap-2 disabled:opacity-50"
        >
          {start.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Start bot
        </button>
      )}

      <div className="inline-flex rounded-lg border border-border bg-card p-1">
        {(["paper", "live"] as const).map((m) => (
          <button
            key={m}
            onClick={() => toggleMode(m)}
            disabled={setMode.isPending}
            className={`px-3 py-1 rounded-md text-xs font-semibold uppercase tracking-wide ${
              mode === m
                ? m === "live"
                  ? "bg-rose-500/20 text-rose-200"
                  : "bg-accent/20 text-accent"
                : "text-muted hover:text-white"
            }`}
          >
            {m}
          </button>
        ))}
      </div>

      {(start.isError || stop.isError || setMode.isError) && (
        <span className="text-sm text-rose-400">
          {(start.error || stop.error || setMode.error)?.message ?? "Action failed"}
        </span>
      )}
    </div>
  );
}
