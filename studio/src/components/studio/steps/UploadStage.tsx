"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Upload,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Video,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useProductionStore } from "@/stores/production";
import { useJobEvents } from "@/lib/useJobEvents";
import { getAccounts, triggerUpload } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

interface UploadStageProps {
  onComplete?: () => void;
}

interface Account {
  id: string;
  nickname: string;
  niche?: string;
  language?: string;
  profile_ready?: boolean;
}

type UploadStatus = "idle" | "uploading" | "done" | "error";

export function UploadStage({ onComplete }: UploadStageProps) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountsLoaded, setAccountsLoaded] = useState(false);
  const [statusMap, setStatusMap] = useState<Record<string, UploadStatus>>({});
  const [confirmAccount, setConfirmAccount] = useState<Account | null>(null);
  const [progressMap, setProgressMap] = useState<Record<string, string>>({});
  const [logMap, setLogMap] = useState<Record<string, string[]>>({});
  const [resultUrl, setResultUrl] = useState<string | null>(null);

  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const jobId = production?.jobId;
  const videoPath = production?.config.videoPath;

  useEffect(() => {
    let cancelled = false;
    getAccounts()
      .then((data) => {
        if (cancelled) return;
        if (Array.isArray(data)) {
          const mapped: Account[] = data.map((a: unknown) => {
            const anyA = a as Record<string, unknown>;
            return {
              id: String(anyA.id ?? anyA.uuid ?? ""),
              nickname: String(anyA.nickname ?? anyA.name ?? "Account"),
              niche: anyA.niche ? String(anyA.niche) : undefined,
              language: anyA.language ? String(anyA.language) : undefined,
              profile_ready: Boolean(anyA.profile_ready),
            };
          });
          setAccounts(mapped);
        }
      })
      .catch(() => setAccounts([]))
      .finally(() => {
        if (!cancelled) setAccountsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Track upload progress: per-account progress message comes from
  // stage.progress events the backend emits while Selenium drives YT Studio.
  // log events also feed into a small per-account log for verbose feedback.
  useJobEvents(jobId ?? null, {
    "stage.start": (e) => {
      if (e.stage !== "upload") return;
      const accountId = (e as unknown as { account_id?: string }).account_id ?? "";
      setProgressMap((m) => ({ ...m, [accountId]: e.message }));
    },
    "stage.progress": (e) => {
      if (e.stage !== "upload") return;
      const accountId = e.account_id ?? "";
      setProgressMap((m) => ({ ...m, [accountId]: e.message }));
    },
    "stage.done": (e) => {
      if (e.stage !== "upload") return;
      const accountId = (e as unknown as { account_id?: string }).account_id ?? "";
      setStatusMap((prev) => ({ ...prev, [accountId]: "done" }));
      const url = (e.artifacts as Record<string, string> | undefined)?.upload_url;
      if (url) setResultUrl(url);
    },
    "stage.error": (e) => {
      if (e.stage !== "upload") return;
      const accountId = (e as unknown as { account_id?: string }).account_id ?? "";
      setStatusMap((prev) => ({ ...prev, [accountId]: "error" }));
      setProgressMap((m) => ({ ...m, [accountId]: e.message }));
    },
    log: (e) => {
      const accountId = (e as unknown as { account_id?: string }).account_id ?? "";
      if (!accountId) return;
      setLogMap((prev) => {
        const cur = prev[accountId] ?? [];
        const next = [...cur, e.message].slice(-8); // keep last 8 lines
        return { ...prev, [accountId]: next };
      });
    },
    done: (e) => {
      const url = (e.artifacts as Record<string, string> | undefined)?.video;
      if (url && url.startsWith("http")) setResultUrl(url);
    },
  });

  const handleConfirm = useCallback(async () => {
    if (!confirmAccount || !jobId) return;
    setStatusMap((prev) => ({ ...prev, [confirmAccount.id]: "uploading" }));
    setProgressMap((m) => ({ ...m, [confirmAccount.id]: "Starting Selenium..." }));
    setConfirmAccount(null);
    try {
      await triggerUpload(jobId, confirmAccount.id);
    } catch (err) {
      setStatusMap((prev) => ({ ...prev, [confirmAccount.id]: "error" }));
      setProgressMap((m) => ({
        ...m,
        [confirmAccount.id]: err instanceof Error ? err.message : String(err),
      }));
    }
  }, [confirmAccount, jobId]);

  if (!jobId) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <div className="rounded-lg border border-error/20 bg-error/10 px-4 py-3 text-sm text-error">
          No active job. Start a production from the Config stage first.
        </div>
      </div>
    );
  }

  if (!videoPath) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <div className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3 text-sm text-text-secondary">
          The video has not finished rendering yet. The Render stage must
          complete before the upload page enables.
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-secondary">YouTube Accounts</h3>
        {resultUrl && (
          <a
            href={resultUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-accent-blue-soft hover:underline"
          >
            View on YouTube <ExternalLink size={12} />
          </a>
        )}
      </div>

      {!accountsLoaded ? (
        <div className="rounded-xl border border-border-ghost bg-surface-raised p-6 text-center text-sm text-text-tertiary">
          Loading accounts...
        </div>
      ) : accounts.length === 0 ? (
        <div className="rounded-xl border border-error/20 bg-error/10 p-6 text-sm text-error">
          No YouTube accounts configured. Add one to <code>.mp/youtube.json</code>{" "}
          (with a logged-in Firefox profile path) before uploading.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {accounts.map((account) => {
            const status = statusMap[account.id] ?? "idle";
            const progress = progressMap[account.id];
            const log = logMap[account.id] ?? [];
            const profileReady = account.profile_ready !== false;

            return (
              <motion.div
                key={account.id}
                className="flex flex-col gap-3 rounded-xl border border-border-ghost bg-surface-raised px-4 py-3 shadow-panel"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-overlay text-text-muted">
                      <Video size={16} />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm text-text-primary">{account.nickname}</span>
                      <div className="flex items-center gap-2 text-[10px] uppercase">
                        {account.niche && (
                          <span className="text-text-tertiary">{account.niche}</span>
                        )}
                        {!profileReady && (
                          <span className="text-error">profile missing</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {status === "done" && (
                      <span className="flex items-center gap-1 text-xs text-success">
                        <CheckCircle2 size={12} /> Done
                      </span>
                    )}
                    {status === "error" && (
                      <span className="flex items-center gap-1 text-xs text-error">
                        <AlertCircle size={12} /> Error
                      </span>
                    )}
                    <motion.button
                      className={cn(
                        "flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-medium transition-colors",
                        status === "done"
                          ? "border border-success/20 bg-success/10 text-success"
                          : "bg-accent-purple text-white shadow-glow-purple hover:bg-accent-purple-deep disabled:opacity-50"
                      )}
                      onClick={() => setConfirmAccount(account)}
                      disabled={
                        status === "uploading" ||
                        status === "done" ||
                        !profileReady
                      }
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                    >
                      {status === "uploading" ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Upload size={14} />
                      )}
                      {status === "done" ? "Uploaded" : "Upload to YouTube"}
                    </motion.button>
                  </div>
                </div>

                {(progress || log.length > 0) && (
                  <div className="flex flex-col gap-1 rounded-lg border border-border-subtle bg-surface-overlay p-3">
                    {progress && (
                      <div className="flex items-center gap-2 text-xs text-text-secondary">
                        {status === "uploading" && (
                          <Loader2 size={12} className="animate-spin shrink-0" />
                        )}
                        <span>{progress}</span>
                      </div>
                    )}
                    {log.length > 0 && (
                      <div className="mt-1 flex flex-col gap-0.5">
                        {log.map((line, i) => (
                          <div key={i} className="font-mono text-[10px] text-text-muted">
                            {line.length > 100 ? line.slice(0, 100) + "..." : line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      <Dialog open={!!confirmAccount} onOpenChange={(open) => { if (!open) setConfirmAccount(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Upload</DialogTitle>
            <DialogDescription>
              This will publish the video to YouTube as {confirmAccount?.nickname}. The
              browser window will stay open until YouTube finishes processing — do not
              close it manually unless the upload fails.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 mt-4">
            <motion.button
              className={cn(
                "rounded-xl border border-border-subtle px-4 py-2 text-sm text-text-secondary transition-colors",
                "hover:bg-surface-overlay hover:text-text-primary"
              )}
              onClick={() => setConfirmAccount(null)}
              whileTap={{ scale: 0.97 }}
            >
              Cancel
            </motion.button>
            <motion.button
              className={cn(
                "rounded-xl bg-accent-purple px-4 py-2 text-sm font-medium text-white shadow-glow-purple transition-colors",
                "hover:bg-accent-purple-deep"
              )}
              onClick={handleConfirm}
              whileTap={{ scale: 0.97 }}
            >
              Upload
            </motion.button>
          </div>
        </DialogContent>
      </Dialog>

      <div className="flex justify-end pt-2">
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl bg-accent-blue px-5 py-2.5 text-sm font-medium text-white shadow-glow-blue transition-colors",
            "hover:bg-accent-blue-soft"
          )}
          onClick={onComplete}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          Done
        </motion.button>
      </div>
    </div>
  );
}
