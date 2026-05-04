"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Image as ImageIcon, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useProductionStore } from "@/stores/production";
import { useJobEvents } from "@/lib/useJobEvents";
import {
  API_BASE,
  continueJob,
  getGateStatus,
  type Stage,
} from "@/lib/api";

interface ImagesStageProps {
  onComplete?: () => void;
}

// Image-prompts editor + preview grid. The backend pauses at the "prompts"
// gate after generating the prompt list — the user can edit/replace each
// prompt before image generation kicks in. Once the user clicks Continue,
// `continueJob` posts the (possibly edited) array back and the runner
// proceeds with `generate_images_batch`.
//
// After images are generated (`stage.done` for "images") the previews
// hydrate from /api/jobs/{id}/artifact/image/{i}.
export function ImagesStage({ onComplete }: ImagesStageProps) {
  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const jobId = production?.jobId;
  // Memoize so it doesn't change identity each render (the `?? []` literal
  // would otherwise create a fresh array reference each call, which makes
  // the useCallback dep array invalidate every render).
  const imagePrompts = useMemo(
    () => production?.config.imagePrompts ?? [],
    [production?.config.imagePrompts]
  );
  const [imagesReady, setImagesReady] = useState(false);
  const [readyMap, setReadyMap] = useState<Record<number, boolean>>({});
  const [awaitingStage, setAwaitingStage] = useState<Stage | null>(null);
  const [resuming, setResuming] = useState(false);

  // Hydrate the gate state on mount in case the SSE awaiting event fired
  // before the component was rendered.
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
      // Backend emits one stage.partial per image prompt as it's produced.
      // We push them into the production store so the user sees them
      // populate live before the gate opens.
      if (e.stage === "prompts" && typeof e.chunk === "string") {
        const store = useProductionStore.getState();
        const cur = store.productions.find((p) => p.id === store.currentProductionId)
          ?.config.imagePrompts ?? [];
        const next = [...cur];
        next[e.index] = e.chunk;
        store.setImagePrompts(next);
      }
    },
    "stage.progress": (e) => {
      if (e.stage === "images" && typeof e.current === "number") {
        // 1-indexed in the event; convert to 0-indexed for the readyMap.
        setReadyMap((prev) => ({ ...prev, [e.current - 1]: true }));
      }
    },
    "stage.done": (e) => {
      if (e.stage === "images") setImagesReady(true);
    },
    "stage.awaiting": (e) => setAwaitingStage(e.stage),
    "stage.resumed": (e) => {
      if (e.stage === awaitingStage) setAwaitingStage(null);
    },
  });

  const handlePromptChange = useCallback((index: number, value: string) => {
    const store = useProductionStore.getState();
    const cur = store.productions.find((p) => p.id === store.currentProductionId)
      ?.config.imagePrompts ?? [];
    const next = cur.map((p, i) => (i === index ? value : p));
    store.setImagePrompts(next);
  }, []);

  const handleContinue = useCallback(async () => {
    if (!jobId) {
      onComplete?.();
      return;
    }
    if (awaitingStage !== "prompts") {
      onComplete?.();
      return;
    }
    setResuming(true);
    try {
      await continueJob(jobId, "prompts", { prompts: imagePrompts });
      onComplete?.();
    } finally {
      setResuming(false);
    }
  }, [jobId, awaitingStage, imagePrompts, onComplete]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-secondary">
          Image Prompts ({imagePrompts.length})
        </h3>
        {awaitingStage === "prompts" && (
          <span className="rounded-full border border-accent-purple/30 bg-accent-purple/10 px-3 py-1 text-[11px] text-accent-purple-soft">
            Edit prompts before generating images
          </span>
        )}
      </div>

      {imagePrompts.length === 0 ? (
        <div className="rounded-xl border border-border-ghost bg-surface-raised p-6 text-center text-sm text-text-tertiary">
          Generating prompts...
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {imagePrompts.map((prompt, index) => (
            <motion.div
              key={index}
              className="flex flex-col gap-3 rounded-xl border border-border-ghost bg-surface-raised p-4 shadow-panel"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <div className="text-[10px] uppercase tracking-wider text-text-muted">
                Prompt {index + 1}
              </div>
              <textarea
                className="w-full resize-y bg-transparent text-xs leading-relaxed text-text-primary outline-none"
                rows={3}
                value={prompt}
                onChange={(e) => handlePromptChange(index, e.target.value)}
              />

              {(imagesReady || readyMap[index]) && jobId ? (
                // Bypass next/image so we don't have to whitelist the API host
                // in next.config.ts; the studio is dev-only / single user.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`${API_BASE}/api/jobs/${jobId}/artifact/image/${index}`}
                  alt={`Image ${index + 1}`}
                  className="aspect-video w-full rounded-lg object-cover"
                />
              ) : (
                <div
                  className="relative aspect-video w-full overflow-hidden rounded-lg"
                  style={{ background: "linear-gradient(135deg, #1E1E32, #0E0E18)" }}
                >
                  <div className="flex h-full items-center justify-center text-text-muted">
                    <ImageIcon size={24} />
                  </div>
                </div>
              )}
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
          disabled={resuming}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          {resuming ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {awaitingStage === "prompts" ? "Apply edits & generate" : "Continue"}
        </motion.button>
      </div>
    </div>
  );
}
