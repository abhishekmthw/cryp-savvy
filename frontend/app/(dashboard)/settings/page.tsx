"use client";

import { useState } from "react";
import { Lock } from "lucide-react";
import {
  useCredentials,
  useDeleteCoindcx,
  useDeleteTelegram,
  useSaveCoindcx,
  useSaveTelegram,
  useTestCoindcx,
  useTestTelegram,
} from "@/hooks/use-api";
import { CredentialSection } from "@/components/settings/credential-section";
import { CoindcxSetupGuide } from "@/components/onboarding/coindcx-setup-guide";

export default function SettingsPage() {
  const { data, isLoading } = useCredentials();

  const saveCoindcx = useSaveCoindcx();
  const deleteCoindcx = useDeleteCoindcx();
  const testCoindcx = useTestCoindcx();

  const saveTelegram = useSaveTelegram();
  const deleteTelegram = useDeleteTelegram();
  const testTelegram = useTestTelegram();

  const [coindcxError, setCoindcxError] = useState<string | null>(null);
  const [telegramError, setTelegramError] = useState<string | null>(null);
  const [coindcxTest, setCoindcxTest] = useState<{ ok: boolean; message: string } | null>(null);
  const [telegramTest, setTelegramTest] = useState<{ ok: boolean; message: string } | null>(null);

  if (isLoading || !data) {
    return <div className="text-muted text-sm">Loading…</div>;
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-muted mt-1">
          API credentials your bot uses. Encrypted at rest with AES-256-GCM —
          even the database operator cannot read them.
        </p>
      </header>

      <div className="bg-accent/5 border border-accent/20 rounded-xl p-4 flex items-start gap-3">
        <Lock className="w-4 h-4 text-accent mt-0.5 shrink-0" />
        <div className="text-sm text-muted">
          Each credential is encrypted with a key unique to your account.
          Saving runs a read-only round-trip against the provider — only verified
          keys are persisted.
        </div>
      </div>

      <CoindcxSetupGuide collapsible defaultOpen={false} />

      <CredentialSection
        title="CoinDCX"
        description="Used to place trades on your CoinDCX account. Restrict the key to trading + read (no withdrawals)."
        status={data.coindcx}
        fields={[
          { name: "api_key",    label: "API Key",    placeholder: "Paste your CoinDCX API Key", type: "password" },
          { name: "api_secret", label: "API Secret", placeholder: "Paste your CoinDCX API Secret", type: "password" },
        ]}
        saving={saveCoindcx.isPending}
        testing={testCoindcx.isPending}
        deleting={deleteCoindcx.isPending}
        saveError={coindcxError}
        testResult={coindcxTest}
        onSave={(v) => {
          setCoindcxError(null);
          setCoindcxTest(null);
          saveCoindcx.mutate(
            { api_key: v.api_key, api_secret: v.api_secret },
            {
              onError: (err: unknown) => {
                const e = err as { detail?: { message?: string } | string };
                const msg = typeof e.detail === "object" ? e.detail?.message : e.detail;
                setCoindcxError(msg ?? "Validation failed — keys not saved.");
              },
            },
          );
        }}
        onTest={() => {
          setCoindcxTest(null);
          testCoindcx.mutate(undefined, {
            onSuccess: (r) => setCoindcxTest(r),
          });
        }}
        onDelete={() => {
          if (confirm("Remove your CoinDCX credentials? Your bot will stop trading.")) {
            deleteCoindcx.mutate();
          }
        }}
      />

      <CredentialSection
        title="Telegram"
        description="Bot used to send trade alerts to your chat. Get a bot token from @BotFather and your chat ID from @userinfobot."
        status={data.telegram}
        fields={[
          { name: "bot_token", label: "Bot Token", placeholder: "1234567890:ABC-DEF...", type: "password" },
          { name: "chat_id",   label: "Chat ID",   placeholder: "Your numeric chat ID", type: "text" },
        ]}
        saving={saveTelegram.isPending}
        testing={testTelegram.isPending}
        deleting={deleteTelegram.isPending}
        saveError={telegramError}
        testResult={telegramTest}
        onSave={(v) => {
          setTelegramError(null);
          setTelegramTest(null);
          saveTelegram.mutate(
            { bot_token: v.bot_token, chat_id: v.chat_id },
            {
              onError: (err: unknown) => {
                const e = err as { detail?: { message?: string } | string };
                const msg = typeof e.detail === "object" ? e.detail?.message : e.detail;
                setTelegramError(msg ?? "Validation failed — credentials not saved.");
              },
            },
          );
        }}
        onTest={() => {
          setTelegramTest(null);
          testTelegram.mutate(undefined, {
            onSuccess: (r) => setTelegramTest(r),
          });
        }}
        onDelete={() => {
          if (confirm("Remove your Telegram credentials? You will stop receiving trade alerts.")) {
            deleteTelegram.mutate();
          }
        }}
      />
    </div>
  );
}
