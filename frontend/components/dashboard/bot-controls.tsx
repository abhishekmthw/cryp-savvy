"use client";

import { useState } from "react";
import { Loader2, Play, Square, ShieldAlert, FlaskConical, Zap } from "lucide-react";

import { useBotStatus, useSetMode, useStartBot, useStopBot } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

export function BotControls() {
  const { data } = useBotStatus();
  const start = useStartBot();
  const stop = useStopBot();
  const setMode = useSetMode();
  const [liveDialogOpen, setLiveDialogOpen] = useState(false);

  const running = data?.is_running ?? false;
  const mode = (data?.mode ?? "paper") as "paper" | "live";

  const error = (start.error || stop.error || setMode.error) as Error | null;

  function confirmLive() {
    setMode.mutate({ mode: "live", confirm: "I_ACCEPT_LIVE_RISK" });
    setLiveDialogOpen(false);
  }

  return (
    <Card className="relative overflow-hidden border-border/60 bg-card/60 backdrop-blur">
      <div className="absolute inset-0 -z-10 bg-grid opacity-40" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-primary/5 via-transparent to-fuchsia-500/5" />
      <CardContent className="flex flex-wrap items-center gap-3 p-5">
        {running ? (
          <Button
            variant="destructive"
            size="default"
            onClick={() => stop.mutate()}
            disabled={stop.isPending}
            className="shadow-md shadow-destructive/20"
          >
            {stop.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Square className="mr-2 h-4 w-4 fill-current" />
            )}
            Stop bot
          </Button>
        ) : (
          <Button
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="bg-gradient-to-r from-primary to-fuchsia-600 text-white shadow-md shadow-primary/25 hover:opacity-95"
          >
            {start.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4 fill-current" />
            )}
            Start bot
          </Button>
        )}

        <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-background/60 p-1">
          {(["paper", "live"] as const).map((m) => {
            const active = mode === m;
            const Icon = m === "paper" ? FlaskConical : Zap;
            return (
              <button
                key={m}
                onClick={() => {
                  if (m === mode) return;
                  if (m === "live") {
                    setLiveDialogOpen(true);
                  } else {
                    setMode.mutate({ mode: "paper" });
                  }
                }}
                disabled={setMode.isPending}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-wide transition-all",
                  active
                    ? m === "live"
                      ? "bg-destructive/15 text-destructive shadow-sm"
                      : "bg-primary/15 text-primary shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {m}
              </button>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          {mode === "live" ? (
            <>
              <ShieldAlert className="h-3.5 w-3.5 text-destructive" />
              Real funds in use
            </>
          ) : (
            <>
              <FlaskConical className="h-3.5 w-3.5 text-primary" />
              Paper-trading sandbox
            </>
          )}
        </div>

        {error && (
          <p className="basis-full text-xs text-destructive">
            {error.message ?? "Action failed"}
          </p>
        )}
      </CardContent>

      <AlertDialog open={liveDialogOpen} onOpenChange={setLiveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-destructive" />
              Switch to LIVE trading?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Your real CoinDCX balance will be used to place trades. The bot
              follows the same strategy as paper mode, but losses are real.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmLive}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              I accept — go live
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
