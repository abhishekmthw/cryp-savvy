"use client";

import { useState } from "react";
import { Check, AlertCircle, Loader2, Pencil, Trash2 } from "lucide-react";
import type { ProviderStatus } from "@/lib/api";
import { formatTs } from "@/lib/utils";

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
}

export function CredentialSection({
  title, description, status, fields,
  saving, testing, deleting,
  saveError, testResult,
  onSave, onTest, onDelete,
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
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <p className="text-sm text-muted mt-1">{description}</p>
        </div>
        <StatusPill status={status} />
      </div>

      {status.present && !editing && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <code className="bg-surface border border-border rounded px-2 py-1 text-muted">
            ••••••{status.last4}
          </code>
          {status.verified_at && (
            <span className="text-muted">
              Verified {formatTs(status.verified_at)}
            </span>
          )}
          <div className="flex-1" />
          <button
            onClick={onTest}
            disabled={testing}
            className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-white/5 text-white inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
            Test now
          </button>
          <button
            onClick={() => setEditing(true)}
            className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-white/5 text-white inline-flex items-center gap-1.5"
          >
            <Pencil className="w-3 h-3" />
            Update
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            className="text-xs px-3 py-1.5 rounded-lg border border-rose-500/40 text-rose-300 hover:bg-rose-500/10 inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <Trash2 className="w-3 h-3" />
            Remove
          </button>
        </div>
      )}

      {testResult && status.present && !editing && (
        <p
          className={`mt-3 text-sm ${
            testResult.ok ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {testResult.ok ? "Verified ✓" : `Failed: ${testResult.message}`}
        </p>
      )}

      {editing && (
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          {fields.map((f) => (
            <div key={f.name}>
              <label className="block text-xs uppercase tracking-wide text-muted mb-1.5">
                {f.label}
              </label>
              <input
                type={f.type ?? "password"}
                placeholder={f.placeholder}
                value={values[f.name]}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.name]: e.target.value }))
                }
                autoComplete="off"
                spellCheck={false}
                className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-muted/60 focus:outline-none focus:border-accent"
              />
            </div>
          ))}

          {saveError && (
            <div className="flex items-start gap-2 text-sm text-rose-400">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{saveError}</span>
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={saving || fields.some((f) => !values[f.name])}
              className="px-4 py-2 rounded-lg bg-accent text-black text-sm font-medium hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save & verify
            </button>
            {status.present && (
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="px-4 py-2 rounded-lg border border-border text-sm text-muted hover:text-white"
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: ProviderStatus }) {
  if (!status.present) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full border border-border text-muted">
        Not configured
      </span>
    );
  }
  if (status.valid) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full border border-emerald-500/40 text-emerald-300 inline-flex items-center gap-1">
        <Check className="w-3 h-3" />
        Verified
      </span>
    );
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded-full border border-amber-500/40 text-amber-300 inline-flex items-center gap-1">
      <AlertCircle className="w-3 h-3" />
      Needs re-verification
    </span>
  );
}
