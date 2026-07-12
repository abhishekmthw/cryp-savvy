"use client";

import { AlertCircle, Loader2, Trash2, TriangleAlert } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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

interface Props {
  clearing: boolean;
  error: string | null;
  onClear: () => void;
}

export function DangerZone({ clearing, error, onClear }: Props) {
  return (
    <Card className="border-destructive/40 bg-card/70 backdrop-blur">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TriangleAlert className="h-4 w-4 text-destructive" />
          Danger zone
        </CardTitle>
        <CardDescription>Irreversible actions for your trading data.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Clear paper trading data</p>
            <p className="text-xs text-muted-foreground">
              Wipe your simulated trading history and start fresh. Credentials,
              bot settings and allocation are kept.
            </p>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive"
                disabled={clearing}
              >
                {clearing ? (
                  <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                ) : (
                  <Trash2 className="mr-1.5 h-3 w-3" />
                )}
                Clear data…
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear all paper trading data?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes your paper trading history and cannot
                  be undone. The following will be erased:
                </AlertDialogDescription>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  <li>All trade history, P&amp;L history and performance stats</li>
                  <li>All open paper positions — discarded immediately, not closed at market</li>
                  <li>Paper order history</li>
                  <li>Per-bucket realized P&amp;L and drawdown state (reset to zero)</li>
                </ul>
                <p className="text-sm text-muted-foreground">
                  Your API credentials, bot settings and capital allocation are
                  kept. If the bot is running it will be stopped and restarted
                  automatically, briefly interrupting scanning.
                </p>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={onClear}
                  disabled={clearing}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {clearing && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                  Yes, clear everything
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
