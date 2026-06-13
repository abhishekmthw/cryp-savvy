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

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

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
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className={cn(collapsible && "cursor-pointer select-none")} onClick={collapsible ? () => setOpen((o) => !o) : undefined}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{collapsible ? "How do I get these keys?" : "Get your CoinDCX API keys"}</CardTitle>
            <CardDescription>
              Step-by-step CoinDCX setup — first time takes 1–3 days.
            </CardDescription>
          </div>
          {collapsible && (
            <ChevronDown
              className={cn(
                "h-5 w-5 shrink-0 text-muted-foreground transition-transform",
                isOpen && "rotate-180"
              )}
            />
          )}
        </div>
      </CardHeader>

      {isOpen && (
        <CardContent className="space-y-4">
          <Step n={1} title="Sign up at coindcx.com">
            <p className="text-sm text-muted-foreground">
              New to CoinDCX? Create your account first.
            </p>
            <ExternalLinkButton href="https://coindcx.com">
              Open coindcx.com
            </ExternalLinkButton>
          </Step>

          <Step n={2} title="Complete KYC (PAN + Aadhaar)">
            <Callout tone="amber">
              Takes <strong>1–3 business days</strong>. The bot can&apos;t trade
              until KYC is verified.
            </Callout>
          </Step>

          <Step n={3} title="Open the API Dashboard">
            <p className="text-sm text-muted-foreground">
              Once verified:{" "}
              <span className="text-foreground">
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
              The <strong>Secret is shown only once</strong>. Copy both before
              closing the dialog — you&apos;ll need to regenerate the key if you
              lose it.
            </Callout>
          </Step>

          <Step n={5} title="Restrict the key's permissions">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 text-sm text-success">
                <Check className="h-4 w-4 shrink-0" />
                Enable: <span className="font-medium">trading + read</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-destructive">
                <X className="h-4 w-4 shrink-0" />
                <span>
                  Do <strong>NOT</strong> enable:{" "}
                  <span className="font-medium">withdrawals</span>
                </span>
              </div>
            </div>
          </Step>

          <Separator />

          <div className="flex items-start gap-2 text-sm text-muted-foreground">
            <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <span>
              Your keys are encrypted at rest with AES-256-GCM using a key
              unique to your account. We never log them.
            </span>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-sm font-semibold text-primary">
        {n}
      </div>
      <div className="flex-1 space-y-2">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {children}
      </div>
    </div>
  );
}

function ExternalLinkButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Button asChild size="sm" variant="outline">
      <a href={href} target="_blank" rel="noreferrer">
        {children}
        <ExternalLink className="ml-1.5 h-3 w-3" />
      </a>
    </Button>
  );
}

function Callout({ tone, children }: { tone: "amber" | "rose"; children: ReactNode }) {
  const styles =
    tone === "amber"
      ? "border-warning/30 bg-warning/5 text-warning"
      : "border-destructive/30 bg-destructive/5 text-destructive";
  return (
    <div className={cn("flex items-start gap-2 rounded-lg border p-2.5 text-sm", styles)}>
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="text-foreground/90">{children}</span>
    </div>
  );
}
