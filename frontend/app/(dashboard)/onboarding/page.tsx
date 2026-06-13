"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Loader2, ArrowRight, Lock, Check } from "lucide-react";

import {
  useCredentials,
  useSaveCoindcx,
  useSaveTelegram,
} from "@/hooks/use-api";
import { CoindcxSetupGuide } from "@/components/onboarding/coindcx-setup-guide";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

export default function OnboardingPage() {
  const router = useRouter();
  const { data } = useCredentials();
  const saveCoindcx = useSaveCoindcx();
  const saveTelegram = useSaveTelegram();

  const [step, setStep] = useState<"coindcx" | "telegram" | "done">("coindcx");
  const [coindcx, setCoindcx] = useState({ api_key: "", api_secret: "" });
  const [telegram, setTelegram] = useState({ bot_token: "", chat_id: "" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data?.coindcx.present) setStep((s) => (s === "coindcx" ? "telegram" : s));
  }, [data?.coindcx.present]);

  function submitCoindcx(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    saveCoindcx.mutate(coindcx, {
      onSuccess: () => setStep("telegram"),
      onError: (err: unknown) => {
        const e2 = err as { detail?: { message?: string } | string };
        const msg = typeof e2.detail === "object" ? e2.detail?.message : e2.detail;
        setError(msg ?? "Validation failed — keys not saved.");
      },
    });
  }

  function submitTelegram(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    saveTelegram.mutate(telegram, {
      onSuccess: () => setStep("done"),
      onError: (err: unknown) => {
        const e2 = err as { detail?: { message?: string } | string };
        const msg = typeof e2.detail === "object" ? e2.detail?.message : e2.detail;
        setError(msg ?? "Validation failed — credentials not saved.");
      },
    });
  }

  return (
    <div className="mx-auto max-w-xl space-y-6 py-2">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Welcome to <span className="text-brand-gradient">CrypSavvy</span></h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Two short steps to get your bot running. Everything is encrypted at rest.
        </p>
      </header>

      <Stepper current={step} />

      {step === "coindcx" && (
        <>
          <CoindcxSetupGuide />
          <Card className="border-border/60 bg-card/70 backdrop-blur">
            <CardHeader>
              <CardTitle>Step 1 — CoinDCX</CardTitle>
              <CardDescription>Paste the API Key and Secret you just created.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submitCoindcx} className="space-y-4">
                <Field
                  id="api_key"
                  label="API Key"
                  value={coindcx.api_key}
                  onChange={(v) => setCoindcx((c) => ({ ...c, api_key: v }))}
                  type="password"
                />
                <Field
                  id="api_secret"
                  label="API Secret"
                  value={coindcx.api_secret}
                  onChange={(v) => setCoindcx((c) => ({ ...c, api_secret: v }))}
                  type="password"
                />

                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <Button
                  type="submit"
                  disabled={!coindcx.api_key || !coindcx.api_secret || saveCoindcx.isPending}
                  className="bg-gradient-to-r from-primary to-fuchsia-600 text-white shadow-md shadow-primary/25 hover:opacity-95"
                >
                  {saveCoindcx.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Save &amp; verify
                </Button>
              </form>
            </CardContent>
          </Card>
        </>
      )}

      {step === "telegram" && (
        <Card className="border-border/60 bg-card/70 backdrop-blur">
          <CardHeader>
            <CardTitle>Step 2 — Telegram (optional)</CardTitle>
            <CardDescription>
              For trade alerts. Create a bot via @BotFather and grab your chat
              ID from @userinfobot. Send your bot any message first so it can reply.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submitTelegram} className="space-y-4">
              <Field
                id="bot_token"
                label="Bot Token"
                value={telegram.bot_token}
                onChange={(v) => setTelegram((t) => ({ ...t, bot_token: v }))}
                type="password"
              />
              <Field
                id="chat_id"
                label="Chat ID"
                value={telegram.chat_id}
                onChange={(v) => setTelegram((t) => ({ ...t, chat_id: v }))}
                type="text"
              />

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <div className="flex items-center gap-2">
                <Button
                  type="submit"
                  disabled={!telegram.bot_token || !telegram.chat_id || saveTelegram.isPending}
                >
                  {saveTelegram.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Save &amp; verify
                </Button>
                <Button type="button" variant="ghost" onClick={() => setStep("done")}>
                  Skip for now
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {step === "done" && (
        <Card className="relative overflow-hidden border-border/60 bg-card/70 backdrop-blur">
          <div className="absolute inset-0 -z-10 bg-gradient-to-br from-primary/10 via-transparent to-fuchsia-500/10" />
          <CardHeader>
            <div className="flex items-start gap-3">
              <span className="rounded-xl border border-primary/40 bg-primary/10 p-2.5">
                <Lock className="h-5 w-5 text-primary" />
              </span>
              <div>
                <CardTitle>You&apos;re ready.</CardTitle>
                <CardDescription className="mt-1">
                  Your bot defaults to <strong className="text-foreground">paper mode</strong>{" "}
                  with ₹10,000 starting balance. Start it from the dashboard whenever
                  you&apos;re ready. You can edit credentials anytime in Settings.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Button
              onClick={() => router.push("/")}
              className="bg-gradient-to-r from-primary to-fuchsia-600 text-white shadow-md shadow-primary/25 hover:opacity-95"
            >
              Open dashboard
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      )}

      <p className="text-center text-xs text-muted-foreground">
        Need to come back later?{" "}
        <Link href="/settings" className="text-primary underline">
          Settings
        </Link>{" "}
        has all the same controls.
      </p>
    </div>
  );
}

function Stepper({ current }: { current: "coindcx" | "telegram" | "done" }) {
  const steps = [
    { id: "coindcx", label: "CoinDCX" },
    { id: "telegram", label: "Telegram" },
    { id: "done", label: "Ready" },
  ];
  const activeIdx = steps.findIndex((s) => s.id === current);
  return (
    <ol className="flex items-center gap-2">
      {steps.map((s, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx;
        return (
          <li key={s.id} className="flex flex-1 items-center gap-2">
            <div
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                active
                  ? "border-primary/50 bg-primary/10 text-primary"
                  : done
                  ? "border-success/40 bg-success/10 text-success"
                  : "border-border bg-muted/30 text-muted-foreground"
              )}
            >
              {done ? (
                <Check className="h-3 w-3" />
              ) : (
                <span className="font-mono">{i + 1}</span>
              )}
              {s.label}
            </div>
            {i < steps.length - 1 && (
              <div
                className={cn(
                  "h-px flex-1 transition-colors",
                  done ? "bg-success/40" : "bg-border"
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: "text" | "password";
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-[11px] uppercase tracking-wider text-muted-foreground">
        {label}
      </Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        spellCheck={false}
      />
    </div>
  );
}
