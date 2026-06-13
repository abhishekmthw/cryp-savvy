"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Loader2, ArrowRight, Lock } from "lucide-react";
import {
  useCredentials,
  useSaveCoindcx,
  useSaveTelegram,
} from "@/hooks/use-api";
import { CoindcxSetupGuide } from "@/components/onboarding/coindcx-setup-guide";

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

  function skipTelegram() {
    setStep("done");
  }

  return (
    <div className="max-w-xl mx-auto py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Welcome to CrypSavvy</h1>
        <p className="text-sm text-muted mt-1">
          Two short steps to get your bot running. Everything is encrypted at rest.
        </p>
      </header>

      <Steps current={step} />

      {step === "coindcx" && (
        <>
          <CoindcxSetupGuide />
          <form
            onSubmit={submitCoindcx}
            className="bg-card border border-border rounded-xl p-5 space-y-4"
          >
            <div>
              <h2 className="text-base font-semibold text-white">Step 1 — CoinDCX</h2>
              <p className="text-sm text-muted mt-1">
                Paste the API Key and Secret you just created.
              </p>
            </div>

            <Field
              label="API Key"
              value={coindcx.api_key}
              onChange={(v) => setCoindcx((c) => ({ ...c, api_key: v }))}
              type="password"
            />
            <Field
              label="API Secret"
              value={coindcx.api_secret}
              onChange={(v) => setCoindcx((c) => ({ ...c, api_secret: v }))}
              type="password"
            />

            {error && <p className="text-sm text-rose-400">{error}</p>}

            <SubmitButton
              label="Save & verify"
              loading={saveCoindcx.isPending}
              disabled={!coindcx.api_key || !coindcx.api_secret}
            />
          </form>
        </>
      )}

      {step === "telegram" && (
        <form
          onSubmit={submitTelegram}
          className="bg-card border border-border rounded-xl p-5 space-y-4"
        >
          <div>
            <h2 className="text-base font-semibold text-white">Step 2 — Telegram (optional)</h2>
            <p className="text-sm text-muted mt-1">
              For trade alerts. Create a bot via @BotFather and grab your chat ID
              from @userinfobot. Send your bot any message first so it can reply.
            </p>
          </div>

          <Field
            label="Bot Token"
            value={telegram.bot_token}
            onChange={(v) => setTelegram((t) => ({ ...t, bot_token: v }))}
            type="password"
          />
          <Field
            label="Chat ID"
            value={telegram.chat_id}
            onChange={(v) => setTelegram((t) => ({ ...t, chat_id: v }))}
            type="text"
          />

          {error && <p className="text-sm text-rose-400">{error}</p>}

          <div className="flex items-center gap-2">
            <SubmitButton
              label="Save & verify"
              loading={saveTelegram.isPending}
              disabled={!telegram.bot_token || !telegram.chat_id}
            />
            <button
              type="button"
              onClick={skipTelegram}
              className="px-4 py-2 rounded-lg border border-border text-sm text-muted hover:text-white"
            >
              Skip for now
            </button>
          </div>
        </form>
      )}

      {step === "done" && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex items-start gap-3">
            <Lock className="w-5 h-5 text-accent mt-0.5 shrink-0" />
            <div>
              <h2 className="text-base font-semibold text-white">You&apos;re ready.</h2>
              <p className="text-sm text-muted mt-1">
                Your bot defaults to <strong className="text-white">paper mode</strong> with
                ₹10,000 starting balance. Start it from the dashboard whenever
                you&apos;re ready. You can edit credentials anytime in Settings.
              </p>
            </div>
          </div>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 rounded-lg bg-accent text-black text-sm font-medium hover:bg-accent/90 inline-flex items-center gap-2"
          >
            Open dashboard
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      )}

      <p className="text-xs text-muted text-center">
        Need to come back later?{" "}
        <Link href="/settings" className="text-accent underline">
          Settings
        </Link>{" "}
        has all the same controls.
      </p>
    </div>
  );
}

function Steps({ current }: { current: "coindcx" | "telegram" | "done" }) {
  const steps = [
    { id: "coindcx",  label: "CoinDCX" },
    { id: "telegram", label: "Telegram" },
    { id: "done",     label: "Ready" },
  ];
  const activeIdx = steps.findIndex((s) => s.id === current);
  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.id} className="flex items-center gap-2">
          <div
            className={`text-xs px-2 py-1 rounded-full border ${
              i <= activeIdx
                ? "border-accent text-accent"
                : "border-border text-muted"
            }`}
          >
            {i + 1}. {s.label}
          </div>
          {i < steps.length - 1 && <div className="w-4 h-px bg-border" />}
        </div>
      ))}
    </div>
  );
}

function Field({
  label, value, onChange, type = "text",
}: { label: string; value: string; onChange: (v: string) => void; type?: "text" | "password" }) {
  return (
    <div>
      <label className="block text-xs uppercase tracking-wide text-muted mb-1.5">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        spellCheck={false}
        className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-muted/60 focus:outline-none focus:border-accent"
      />
    </div>
  );
}

function SubmitButton({
  label, loading, disabled,
}: { label: string; loading: boolean; disabled: boolean }) {
  return (
    <button
      type="submit"
      disabled={disabled || loading}
      className="px-4 py-2 rounded-lg bg-accent text-black text-sm font-medium hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {label}
    </button>
  );
}
