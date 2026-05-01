"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Upload, CheckCircle2, AlertCircle, Loader2, Video } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadStageProps {
  onComplete?: () => void;
}

interface Account {
  id: string;
  nickname: string;
  platform: string;
}

type UploadStatus = "idle" | "uploading" | "done" | "error";

const FALLBACK_ACCOUNTS: Account[] = [
  { id: "a1", nickname: "Main Channel", platform: "youtube" },
  { id: "a2", nickname: "Clips Archive", platform: "youtube" },
];

export function UploadStage({ onComplete }: UploadStageProps) {
  const [accounts, setAccounts] = useState<Account[]>(FALLBACK_ACCOUNTS);
  const [statusMap, setStatusMap] = useState<Record<string, UploadStatus>>({});

  useEffect(() => {
    fetch("http://localhost:8000/api/accounts")
      .then((r) => r.ok ? r.json() : FALLBACK_ACCOUNTS)
      .then((data: { accounts: Account[] }) => setAccounts(data.accounts || FALLBACK_ACCOUNTS))
      .catch(() => setAccounts(FALLBACK_ACCOUNTS));
  }, []);

  const handleUpload = useCallback(async (id: string) => {
    try {
      setStatusMap((prev) => ({ ...prev, [id]: "uploading" }));
      await new Promise((resolve) => setTimeout(resolve, 2000));
      setStatusMap((prev) => ({ ...prev, [id]: "done" }));
    } catch {
      setStatusMap((prev) => ({ ...prev, [id]: "error" }));
    }
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      <h3 className="text-sm font-medium text-text-secondary">YouTube Accounts</h3>

      <div className="flex flex-col gap-3">
        {accounts.map((account) => {
          const status = statusMap[account.id] ?? "idle";
          return (
            <motion.div
              key={account.id}
              className="flex items-center justify-between rounded-xl border border-border-ghost bg-surface-raised px-4 py-3 shadow-panel"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-overlay text-text-muted">
                  <Video size={16} />
                </div>
                <div className="flex flex-col">
                  <span className="text-sm text-text-primary">{account.nickname}</span>
                  <span className="text-[10px] text-text-tertiary uppercase">{account.platform}</span>
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
                  onClick={() => handleUpload(account.id)}
                  disabled={status === "uploading" || status === "done"}
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
            </motion.div>
          );
        })}
      </div>

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
