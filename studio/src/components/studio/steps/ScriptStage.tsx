"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useProductionStore } from "@/stores/production";
import { useJobEvents } from "@/lib/useJobEvents";
import { continueJob, getGateStatus, type Stage } from "@/lib/api";

interface ScriptStageProps {
  onComplete?: () => void;
}

// Stage where the script is rendered as one editable textarea per paragraph.
// The wizard pauses here on the backend (run_short_job calls
// jobs.pause_at(job_id, "script")) until the user clicks Continue, which
// POSTs the edited paragraphs back so the next stage uses them.
export function ScriptStage({ onComplete }: ScriptStageProps) {
  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const jobId = production?.jobId;
  const script = production?.config.script ?? "";

  // `awaitingStage` mirrors the backend's gate. When it equals "script"
  // the Continue button activates. We listen to `stage.awaiting` events
  // AND fall back to GET /api/jobs/{id}/gate on mount in case the SSE
  // event arrived before this component was rendered.
  const [awaitingStage, setAwaitingStage] = useState<Stage | null>(null);
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    getGateStatus(jobId)
      .then(({ awaiting }) => {
        if (!cancelled) setAwaitingStage(awaiting);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useJobEvents(jobId ?? null, {
    "stage.partial": (e) => {
      if (e.stage === "script" && typeof e.chunk === "string") {
        const store = useProductionStore.getState();
        const current =
          store.productions.find((p) => p.id === store.currentProductionId)?.config.script ?? "";
        // Section index is `e.index`; rebuild the script as paragraphs.
        const parts = current ? current.split("\n\n") : [];
        parts[e.index] = e.chunk;
        store.setScript(parts.join("\n\n"));
      }
    },
    "stage.done": (e) => {
      if (e.stage === "script") {
        useProductionStore.getState().setStageStatus("script", "done");
      }
    },
    "stage.awaiting": (e) => {
      setAwaitingStage(e.stage);
    },
    "stage.resumed": (e) => {
      if (e.stage === awaitingStage) setAwaitingStage(null);
    },
    "stage.error": (e) => {
      if (e.stage === "script") {
        useProductionStore.getState().setStageStatus("script", "error", e.message);
      }
    },
  });

  // Paragraph split must match `runners._split_paragraphs` (split on \n\n).
  const paragraphs = script ? script.split("\n\n").filter((p) => p.trim().length > 0) : [];

  const handleParagraphChange = useCallback((index: number, value: string) => {
    const store = useProductionStore.getState();
    const current =
      store.productions.find((p) => p.id === store.currentProductionId)?.config.script ?? "";
    const parts = current ? current.split("\n\n") : [];
    parts[index] = value;
    store.setScript(parts.join("\n\n"));
  }, []);

  const handleContinue = useCallback(async () => {
    if (!jobId) {
      onComplete?.();
      return;
    }
    if (awaitingStage !== "script") {
      // No gate to release — just locally advance.
      onComplete?.();
      return;
    }
    setResuming(true);
    try {
      await continueJob(jobId, "script", { script });
      onComplete?.();
    } catch (err) {
      // Surface the backend error so the user knows the gate didn't release.
      useProductionStore
        .getState()
        .setStageStatus("script", "error", err instanceof Error ? err.message : String(err));
    } finally {
      setResuming(false);
    }
  }, [jobId, awaitingStage, script, onComplete]);

  const buttonLabel = (() => {
    if (resuming) return "Saving...";
    if (awaitingStage === "script") return "Apply edits & continue";
    return "Continue";
  })();
  const buttonDisabled = resuming;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-text-secondary">
          Topic: {production?.config.topic || "—"}
        </span>
        {awaitingStage === "script" && (
          <span className="rounded-full border border-accent-purple/30 bg-accent-purple/10 px-3 py-1 text-[11px] text-accent-purple-soft">
            Awaiting your review
          </span>
        )}
      </div>

      {paragraphs.length === 0 ? (
        <div className="rounded-xl border border-border-ghost bg-surface-raised p-6 text-center text-sm text-text-tertiary">
          Generating script...
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {paragraphs.map((paragraph, index) => (
            <motion.div
              key={index}
              className="rounded-xl border border-border-ghost bg-surface-raised p-4 shadow-panel"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.06 }}
            >
              <div className="mb-1.5 text-[10px] uppercase tracking-wider text-text-muted">
                Section {index + 1}
              </div>
              <textarea
                className="w-full resize-y bg-transparent text-sm leading-relaxed text-text-primary outline-none"
                rows={Math.max(2, Math.min(6, Math.ceil(paragraph.length / 80)))}
                value={paragraph}
                onChange={(e) => handleParagraphChange(index, e.target.value)}
              />
            </motion.div>
          ))}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl bg-accent-blue px-5 py-2.5 text-sm font-medium text-white shadow-glow-blue transition-colors",
            "hover:bg-accent-blue-soft disabled:opacity-50"
          )}
          onClick={handleContinue}
          disabled={buttonDisabled}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          {resuming ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {buttonLabel}
        </motion.button>
      </div>
    </div>
  );
}
