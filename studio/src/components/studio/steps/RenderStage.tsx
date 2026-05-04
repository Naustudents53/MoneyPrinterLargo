"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { XCircle, ArrowRight, CheckCircle2, FileVideo } from "lucide-react";
import { cn } from "@/lib/utils";
import { useProductionStore } from "@/stores/production";
import { useJobEvents } from "@/lib/useJobEvents";
import { cancelJob, API_BASE, type Stage } from "@/lib/api";

interface RenderStageProps {
  onComplete?: () => void;
}

const STAGE_LABELS: Record<string, string> = {
  topic: "Topic",
  script: "Script",
  metadata: "Metadata",
  prompts: "Image prompts",
  images: "Images",
  thumbnail: "Thumbnail",
  tts: "Narration",
  render: "Final video",
};

export function RenderStage({ onComplete }: RenderStageProps) {
  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const jobId = production?.jobId;
  const jobStatus = production?.jobStatus;
  const jobProgress = production?.jobProgress ?? 0;

  const [activeStage, setActiveStage] = useState<Stage | null>(null);
  const [activeMessage, setActiveMessage] = useState<string>("");

  useJobEvents(jobId ?? null, {
    "stage.start": (e) => {
      setActiveStage(e.stage);
      setActiveMessage(e.message);
    },
    "stage.progress": (e) => {
      // For "render" the percent is meaningful; for "images" it's the
      // image counter. Either way we treat it as the headline progress
      // for the bar.
      if (typeof e.percent === "number" && e.percent > 0) {
        useProductionStore.getState().setJobProgress(Number(e.percent));
      }
      setActiveStage(e.stage);
      setActiveMessage(e.message);
    },
    "stage.done": (e) => {
      if (e.stage === "render") {
        useProductionStore.getState().setJobStatus("done");
        useProductionStore
          .getState()
          .setVideoPath(`${API_BASE}/api/jobs/${jobId}/artifact/video`);
      }
    },
    "stage.error": (e) => {
      useProductionStore.getState().setJobStatus("error");
      setActiveMessage(e.message);
    },
    done: (e) => {
      useProductionStore.getState().setJobStatus("done");
      const url = (e.artifacts as Record<string, string> | undefined)?.video;
      if (url) useProductionStore.getState().setVideoPath(url);
    },
    cancelled: () => {
      useProductionStore.getState().setJobStatus("cancelled");
    },
  });

  const statusText = useMemo(() => {
    if (jobStatus === "done") return "Render Complete";
    if (jobStatus === "error") return "Render Error";
    if (jobStatus === "cancelled") return "Cancelled by user";
    if (activeStage && STAGE_LABELS[activeStage]) {
      return `${STAGE_LABELS[activeStage]}${activeMessage ? " — " + activeMessage : ""}`;
    }
    if (jobStatus === "running") return "Rendering...";
    return "Waiting...";
  }, [jobStatus, activeStage, activeMessage]);

  const done = jobStatus === "done";
  const cancelled = jobStatus === "cancelled";

  return (
    <div className="flex flex-col items-center gap-8 p-6">
      <div className="w-full max-w-2xl">
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
          <motion.div
            className="h-full rounded-full"
            style={{
              background: "linear-gradient(90deg, #E8A24F, #3B82F6)",
              boxShadow: "0 0 20px rgba(232,162,79,0.2)",
            }}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(jobProgress, 100)}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-text-tertiary">
          <span>{Math.round(jobProgress)}%</span>
          <span className="text-text-secondary">{statusText}</span>
        </div>
      </div>

      <motion.div
        className={cn(
          "flex w-full max-w-2xl flex-col items-center gap-4 rounded-2xl border p-8 text-center shadow-panel",
          done
            ? "border-success/20 bg-success/5"
            : cancelled
              ? "border-error/20 bg-error/5"
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
          <span className="text-lg font-medium text-text-primary">{statusText}</span>
          {done && (
            <span className="text-xs text-text-tertiary">
              <span className="inline-flex items-center gap-1.5">
                <FileVideo size={12} />
                Video ready
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
            onClick={() => {
              if (jobId) cancelJob(jobId);
            }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
          >
            <XCircle size={14} />
            Cancel
          </motion.button>
        )}

        {cancelled && <span className="text-xs text-error">Cancelled by user</span>}
      </motion.div>

      {production?.config.videoPath && (
        <video
          src={production.config.videoPath}
          controls
          className="w-full max-w-2xl rounded-xl"
        />
      )}

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
