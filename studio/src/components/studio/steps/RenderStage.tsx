"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { XCircle, ArrowRight, CheckCircle2, FileVideo } from "lucide-react";
import { cn } from "@/lib/utils";

interface RenderStageProps {
  onComplete?: () => void;
}

const STATUSES = [
  "Queued...",
  "Generating script...",
  "Generating images (3/12)...",
  "Rendering...",
  "Encoding audio...",
  "Export complete",
];

export function RenderStage({ onComplete }: RenderStageProps) {
  const [progress, setProgress] = useState(0);
  const [statusIndex, setStatusIndex] = useState(0);
  const [cancelled, setCancelled] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (cancelled || done) return;
    const interval = setInterval(() => {
      setProgress((prev) => {
        const next = prev + Math.random() * 12;
        if (next >= 100) {
          clearInterval(interval);
          setStatusIndex(STATUSES.length - 1);
          setDone(true);
          return 100;
        }
        const nextIndex = Math.min(Math.floor((next / 100) * (STATUSES.length - 1)), STATUSES.length - 2);
        setStatusIndex(nextIndex);
        return next;
      });
    }, 800);
    return () => clearInterval(interval);
  }, [cancelled, done]);

  return (
    <div className="flex flex-col items-center gap-8 p-6">
      {/* Progress bar */}
      <div className="w-full max-w-2xl">
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
          <motion.div
            className="h-full rounded-full"
            style={{
              background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
              boxShadow: "0 0 20px rgba(124,58,237,0.2)",
            }}
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-text-tertiary">
          <span>{Math.round(progress)}%</span>
          <span className="text-text-secondary">{STATUSES[statusIndex]}</span>
        </div>
      </div>

      {/* Status card */}
      <motion.div
        className={cn(
          "flex w-full max-w-2xl flex-col items-center gap-4 rounded-2xl border p-8 text-center shadow-panel",
          done
            ? "border-success/20 bg-success/5"
            : "border-border-ghost bg-surface-raised"
        )}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
      >
        {done ? (
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 200 }}
          >
            <CheckCircle2 size={40} className="text-success" />
          </motion.div>
        ) : (
          <div className="flex h-12 w-12 items-center justify-center">
            <motion.div
              className="h-8 w-8 rounded-full border-2 border-accent-purple border-t-transparent"
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            />
          </div>
        )}

        <div className="flex flex-col gap-1">
          <span className="text-lg font-medium text-text-primary">
            {done ? "Export Complete" : STATUSES[statusIndex]}
          </span>
          {done && (
            <span className="text-xs text-text-tertiary">
              <span className="inline-flex items-center gap-1.5">
                <FileVideo size={12} />
                /projects/output/final_video.mp4
              </span>
            </span>
          )}
        </div>

        {!done && !cancelled && (
          <motion.button
            className={cn(
              "flex items-center gap-2 rounded-xl border border-error/20 bg-error/10 px-4 py-2 text-xs text-error transition-colors",
              "hover:bg-error/20"
            )}
            onClick={() => setCancelled(true)}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
          >
            <XCircle size={14} />
            Cancel
          </motion.button>
        )}

        {cancelled && (
          <span className="text-xs text-error">Cancelled by user</span>
        )}
      </motion.div>

      {done && (
        <motion.div
          className="flex justify-end"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
        >
          <motion.button
            className={cn(
              "flex items-center gap-2 rounded-xl bg-accent-blue px-5 py-2.5 text-sm font-medium text-white shadow-glow-blue transition-colors",
              "hover:bg-accent-blue-soft"
            )}
            onClick={onComplete}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
          >
            Continue
            <ArrowRight size={16} />
          </motion.button>
        </motion.div>
      )}
    </div>
  );
}
