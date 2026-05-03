"use client";

import { useState, type ReactNode } from "react";
import {
  AlertCircle,
  ChevronDown,
  ExternalLink,
  Lock,
  Check,
  X,
} from "lucide-react";

interface Props {
  defaultOpen?: boolean;
  collapsible?: boolean;
}

export function CoindcxSetupGuide({
  defaultOpen = true,
  collapsible = false,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const isOpen = collapsible ? open : true;

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      {collapsible ? (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between text-left"
          aria-expanded={isOpen}
        >
          <div>
            <h3 className="text-base font-semibold text-white">
              How do I get these keys?
            </h3>
            <p className="text-sm text-muted mt-1">
              Step-by-step CoinDCX setup — first time takes 1–3 days.
            </p>
          </div>
          <ChevronDown
            className={`w-5 h-5 text-muted transition-transform shrink-0 ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </button>
      ) : (
        <header>
          <h3 className="text-base font-semibold text-white">
            Get your CoinDCX API keys
          </h3>
          <p className="text-sm text-muted mt-1">
            Step-by-step — first time takes 1–3 days.
          </p>
        </header>
      )}

      {isOpen && (
        <div className="mt-5 space-y-4">
          <Step n={1} title="Sign up at coindcx.com">
            <p className="text-sm text-muted">
              New to CoinDCX? Create your account first.
            </p>
            <ExternalLinkButton href="https://coindcx.com">
              Open coindcx.com
            </ExternalLinkButton>
          </Step>

          <Step n={2} title="Complete KYC (PAN + Aadhaar)">
            <Callout tone="amber">
              Takes <strong className="text-amber-200">1–3 business days</strong>.
              The bot can&apos;t trade until KYC is verified.
            </Callout>
          </Step>

          <Step n={3} title="Open the API Dashboard">
            <p className="text-sm text-muted">
              Once verified:{" "}
              <span className="text-white">
                Profile → API Dashboard → Create New API Key
              </span>
              .
            </p>
            <ExternalLinkButton href="https://coindcx.com/settings/api">
              Open API Dashboard
            </ExternalLinkButton>
          </Step>

          <Step n={4} title="Copy your API Key and API Secret">
            <Callout tone="amber">
              The <strong className="text-amber-200">Secret is shown only once</strong>.
              Copy both before closing the dialog — you&apos;ll need to regenerate the
              key if you lose it.
            </Callout>
          </Step>

          <Step n={5} title="Restrict the key's permissions">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 text-sm text-emerald-300">
                <Check className="w-4 h-4 shrink-0" />
                Enable: <span className="font-medium">trading + read</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-rose-300">
                <X className="w-4 h-4 shrink-0" />
                <span>
                  Do <strong>NOT</strong> enable:{" "}
                  <span className="font-medium">withdrawals</span>
                </span>
              </div>
            </div>
          </Step>

          <div className="flex items-start gap-2 pt-2 border-t border-border text-sm text-muted">
            <Lock className="w-4 h-4 text-accent mt-0.5 shrink-0" />
            <span>
              Your keys are encrypted at rest with AES-256-GCM using a key unique
              to your account. We never log them.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-7 h-7 rounded-full border border-accent text-accent text-sm font-medium flex items-center justify-center shrink-0">
        {n}
      </div>
      <div className="flex-1 space-y-2">
        <p className="text-sm font-medium text-white">{title}</p>
        {children}
      </div>
    </div>
  );
}

function ExternalLinkButton({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-white/5 text-white"
    >
      {children}
      <ExternalLink className="w-3 h-3" />
    </a>
  );
}

function Callout({
  tone,
  children,
}: {
  tone: "amber" | "rose";
  children: ReactNode;
}) {
  const styles =
    tone === "amber"
      ? "border-amber-500/30 bg-amber-500/5 text-amber-300"
      : "border-rose-500/30 bg-rose-500/5 text-rose-300";
  return (
    <div
      className={`flex items-start gap-2 text-sm rounded-lg border p-2.5 ${styles}`}
    >
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
      <span>{children}</span>
    </div>
  );
}
