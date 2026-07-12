"use client";

import { useState } from "react";
import { Lock } from "lucide-react";
import { toast } from "sonner";

import {
  useClearPaperData,
  useCredentials,
  useDeleteCoindcx,
  useDeleteTelegram,
  useSaveCoindcx,
  useSaveTelegram,
  useTestCoindcx,
  useTestTelegram,
} from "@/hooks/use-api";
import { CredentialSection } from "@/components/settings/credential-section";
import { DangerZone } from "@/components/settings/danger-zone";
import { CoindcxSetupGuide } from "@/components/onboarding/coindcx-setup-guide";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsPage() {
  const { data, isLoading } = useCredentials();

  const saveCoindcx = useSaveCoindcx();
  const deleteCoindcx = useDeleteCoindcx();
  const testCoindcx = useTestCoindcx();

  const saveTelegram = useSaveTelegram();
  const deleteTelegram = useDeleteTelegram();
  const testTelegram = useTestTelegram();

  const clearData = useClearPaperData();

  const [coindcxError, setCoindcxError] = useState<string | null>(null);
  const [telegramError, setTelegramError] = useState<string | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);
  const [coindcxTest, setCoindcxTest] = useState<{ ok: boolean; message: string } | null>(null);
  const [telegramTest, setTelegramTest] = useState<{ ok: boolean; message: string } | null>(null);

  if (isLoading || !data) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-4 w-72" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Alert className="border-primary/30 bg-primary/5">
        <Lock className="h-4 w-4 text-primary" />
        <AlertTitle className="text-foreground">Encrypted at rest</AlertTitle>
        <AlertDescription>
          Each credential is encrypted with a key unique to your account. Saving
          runs a read-only round-trip against the provider — only verified keys
          are persisted.
        </AlertDescription>
      </Alert>

      <CoindcxSetupGuide collapsible defaultOpen={false} />

      <CredentialSection
        title="CoinDCX"
        description="Used to place trades on your CoinDCX account. Restrict the key to trading + read (no withdrawals)."
        status={data.coindcx}
        fields={[
          { name: "api_key", label: "API Key", placeholder: "Paste your CoinDCX API Key", type: "password" },
          { name: "api_secret", label: "API Secret", placeholder: "Paste your CoinDCX API Secret", type: "password" },
        ]}
        saving={saveCoindcx.isPending}
        testing={testCoindcx.isPending}
        deleting={deleteCoindcx.isPending}
        saveError={coindcxError}
        testResult={coindcxTest}
        deleteConfirmation="Your bot will stop trading until you add new keys. This cannot be undone."
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
        onDelete={() => deleteCoindcx.mutate()}
      />

      <CredentialSection
        title="Telegram"
        description="Bot used to send trade alerts to your chat. Get a bot token from @BotFather and your chat ID from @userinfobot."
        status={data.telegram}
        fields={[
          { name: "bot_token", label: "Bot Token", placeholder: "1234567890:ABC-DEF...", type: "password" },
          { name: "chat_id", label: "Chat ID", placeholder: "Your numeric chat ID", type: "text" },
        ]}
        saving={saveTelegram.isPending}
        testing={testTelegram.isPending}
        deleting={deleteTelegram.isPending}
        saveError={telegramError}
        testResult={telegramTest}
        deleteConfirmation="You will stop receiving trade alerts. This cannot be undone."
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
        onDelete={() => deleteTelegram.mutate()}
      />

      <DangerZone
        clearing={clearData.isPending}
        error={clearError}
        onClear={() => {
          if (clearData.isPending) return;
          setClearError(null);
          clearData.mutate(undefined, {
            onSuccess: (r) => {
              if (r.warning) {
                toast.warning(r.warning);
              } else {
                toast.success("Paper trading data cleared", {
                  description: `Deleted ${r.deleted.trades} trades, ${r.deleted.positions} open positions and ${r.deleted.orders} orders.`,
                });
              }
            },
            onError: (err: unknown) => {
              const e = err as { detail?: unknown; message?: string };
              setClearError(
                typeof e.detail === "string"
                  ? e.detail
                  : e.message ?? "Failed to clear data.",
              );
            },
          });
        }}
      />
    </div>
  );
}
