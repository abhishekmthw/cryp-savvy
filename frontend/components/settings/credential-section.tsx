"use client";

import { useState } from "react";
import { Check, AlertCircle, Loader2, Pencil, Trash2 } from "lucide-react";

import type { ProviderStatus } from "@/lib/api";
import { formatTs, cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export interface FieldDef {
  name: string;
  label: string;
  placeholder?: string;
  type?: "text" | "password";
}

interface Props {
  title: string;
  description: string;
  status: ProviderStatus;
  fields: FieldDef[];
  saving: boolean;
  testing: boolean;
  deleting: boolean;
  saveError: string | null;
  testResult: { ok: boolean; message: string } | null;
  onSave: (values: Record<string, string>) => void;
  onTest: () => void;
  onDelete: () => void;
  deleteConfirmation: string;
}

export function CredentialSection({
  title,
  description,
  status,
  fields,
  saving,
  testing,
  deleting,
  saveError,
  testResult,
  onSave,
  onTest,
  onDelete,
  deleteConfirmation,
}: Props) {
  const [editing, setEditing] = useState(!status.present);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.name, ""])),
  );

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave(values);
  }

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <StatusPill status={status} />
      </CardHeader>
      <CardContent>
        {status.present && !editing && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <code className="rounded border border-border/60 bg-muted/50 px-2 py-1 font-mono text-xs text-muted-foreground">
              ••••••{status.last4}
            </code>
            {status.verified_at && (
              <span className="text-xs text-muted-foreground">
                Verified {formatTs(status.verified_at)}
              </span>
            )}
            <div className="flex-1" />
            <Button
              size="sm"
              variant="outline"
              onClick={onTest}
              disabled={testing}
            >
              {testing && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
              Test now
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing(true)}
            >
              <Pencil className="mr-1.5 h-3 w-3" />
              Update
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10 hover:text-destructive">
                  <Trash2 className="mr-1.5 h-3 w-3" />
                  Remove
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Remove {title} credentials?</AlertDialogTitle>
                  <AlertDialogDescription>{deleteConfirmation}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={onDelete}
                    disabled={deleting}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    {deleting && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                    Remove
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}

        {testResult && status.present && !editing && (
          <p
            className={cn(
              "mt-3 text-sm",
              testResult.ok ? "text-success" : "text-destructive"
            )}
          >
            {testResult.ok ? "Verified ✓" : `Failed: ${testResult.message}`}
          </p>
        )}

        {editing && (
          <form onSubmit={handleSubmit} className="space-y-3">
            {fields.map((f) => (
              <div key={f.name} className="space-y-1.5">
                <Label
                  htmlFor={f.name}
                  className="text-[11px] uppercase tracking-wider text-muted-foreground"
                >
                  {f.label}
                </Label>
                <Input
                  id={f.name}
                  type={f.type ?? "password"}
                  placeholder={f.placeholder}
                  value={values[f.name]}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [f.name]: e.target.value }))
                  }
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>
            ))}

            {saveError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}

            <div className="flex items-center gap-2 pt-1">
              <Button
                type="submit"
                disabled={saving || fields.some((f) => !values[f.name])}
              >
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save &amp; verify
              </Button>
              {status.present && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </Button>
              )}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function StatusPill({ status }: { status: ProviderStatus }) {
  if (!status.present) {
    return (
      <Badge variant="outline" className="border-border bg-muted/30 text-muted-foreground">
        Not configured
      </Badge>
    );
  }
  if (status.valid) {
    return (
      <Badge variant="outline" className="gap-1 border-success/40 bg-success/10 text-success">
        <Check className="h-3 w-3" />
        Verified
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 border-warning/40 bg-warning/10 text-warning">
      <AlertCircle className="h-3 w-3" />
      Needs re-verification
    </Badge>
  );
}
