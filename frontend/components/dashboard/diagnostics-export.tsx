"use client";

/**
 * Export toolbar for the diagnostics page.
 *
 * "Copy for Claude" puts the full markdown diagnostics report on the clipboard
 * so it can be pasted straight into Claude Code as context for the next round
 * of strategy improvements. The .md / .json buttons download the same report
 * as files (Blob + object URL — no dependencies).
 */

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { ClipboardCopy, FileDown, FileJson, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function dateStamp() {
  return new Date().toISOString().slice(0, 10);
}

export function DiagnosticsExport() {
  const { getToken } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);

  async function withToken<T>(action: string, fn: (token: string) => Promise<T>) {
    setBusy(action);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return await fn(token);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Export failed — is the backend up?",
      );
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  const copyForClaude = () =>
    withToken("copy", async (token) => {
      const md = await api.diagnosticsExportMarkdown(token);
      await navigator.clipboard.writeText(md);
      toast.success("Report copied — paste it into Claude Code");
    });

  const downloadMd = () =>
    withToken("md", async (token) => {
      const md = await api.diagnosticsExportMarkdown(token);
      downloadBlob(md, `crypsavvy-diagnostics-${dateStamp()}.md`, "text/markdown");
      toast.success("Markdown report downloaded");
    });

  const downloadJson = () =>
    withToken("json", async (token) => {
      const data = await api.diagnosticsExportJson(token);
      downloadBlob(
        JSON.stringify(data, null, 2),
        `crypsavvy-diagnostics-${dateStamp()}.json`,
        "application/json",
      );
      toast.success("JSON report downloaded");
    });

  const spinner = <Loader2 className="h-4 w-4 animate-spin" />;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="default" size="sm" onClick={copyForClaude} disabled={busy !== null}>
        {busy === "copy" ? spinner : <ClipboardCopy className="h-4 w-4" />}
        <span className="ml-2">Copy for Claude</span>
      </Button>
      <Button variant="outline" size="sm" onClick={downloadMd} disabled={busy !== null}>
        {busy === "md" ? spinner : <FileDown className="h-4 w-4" />}
        <span className="ml-2">Download .md</span>
      </Button>
      <Button variant="outline" size="sm" onClick={downloadJson} disabled={busy !== null}>
        {busy === "json" ? spinner : <FileJson className="h-4 w-4" />}
        <span className="ml-2">Download .json</span>
      </Button>
    </div>
  );
}
