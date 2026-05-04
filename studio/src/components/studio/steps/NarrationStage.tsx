"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Play, ArrowRight, Loader2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useProductionStore } from "@/stores/production";
import { useJobEvents } from "@/lib/useJobEvents";
import {
  API_BASE,
  continueJob,
  getGateStatus,
  getVoices,
  ttsPreview,
  type Stage,
} from "@/lib/api";

interface NarrationStageProps {
  onComplete?: () => void;
}

interface VoiceItem {
  id: string;
  alias: string;
}

export function NarrationStage({ onComplete }: NarrationStageProps) {
  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const jobId = production?.jobId;
  const configVoiceId = production?.config.voiceId ?? "";
  const previewText =
    production?.config.script?.split("\n\n")[0]?.slice(0, 140) ??
    "This is a preview of the selected voice.";

  const [voices, setVoices] = useState<VoiceItem[]>([]);
  const [selectedVoice, setSelectedVoice] = useState(configVoiceId);
  const [drama, setDrama] = useState(50);
  const [pacing, setPacing] = useState(50);
  const [previewing, setPreviewing] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [awaitingStage, setAwaitingStage] = useState<Stage | null>(null);
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    getVoices()
      .then((data) => {
        if (data && Array.isArray(data.voices)) {
          const mapped: VoiceItem[] = data.voices.map((v: unknown) => {
            const anyV = v as Record<string, unknown>;
            return {
              id: String(anyV.id ?? ""),
              alias: String(anyV.alias ?? anyV.name ?? anyV.id ?? ""),
            };
          });
          setVoices(mapped);
          if (configVoiceId) setSelectedVoice(configVoiceId);
          else if (data.default) setSelectedVoice(data.default);
        }
      })
      .catch(() => setVoices([]));
  }, [configVoiceId]);

  // Hydrate gate state on mount.
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
    "stage.done": (e) => {
      if (e.stage === "tts") setAudioReady(true);
    },
    "stage.awaiting": (e) => setAwaitingStage(e.stage),
    "stage.resumed": (e) => {
      if (e.stage === awaitingStage) setAwaitingStage(null);
    },
  });

  // BUG FIX (S6): the previous version called ttsPreview(voiceId, text) —
  // the signature is ttsPreview(text, voice_id).
  const handlePreview = useCallback(async () => {
    if (!selectedVoice) return;
    try {
      setPreviewing(true);
      await ttsPreview(previewText, selectedVoice);
    } catch {
      // noop — preview is non-essential
    } finally {
      setPreviewing(false);
    }
  }, [selectedVoice, previewText]);

  const handleContinue = useCallback(async () => {
    if (!jobId) {
      onComplete?.();
      return;
    }
    if (awaitingStage !== "narration") {
      onComplete?.();
      return;
    }
    setResuming(true);
    try {
      await continueJob(jobId, "narration", {
        voice_id: selectedVoice,
        drama,
        pacing,
      });
      onComplete?.();
    } finally {
      setResuming(false);
    }
  }, [jobId, awaitingStage, selectedVoice, drama, pacing, onComplete]);

  return (
    <div className="flex flex-col gap-6 p-6">
      {awaitingStage === "narration" && (
        <div className="flex justify-end">
          <span className="rounded-full border border-accent-purple/30 bg-accent-purple/10 px-3 py-1 text-[11px] text-accent-purple-soft">
            Listen, then continue to render
          </span>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Voice</label>
        <div className="relative">
          <select
            className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={selectedVoice}
            onChange={(e) => setSelectedVoice(e.target.value)}
          >
            <option value="">Select voice</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.alias}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
            size={16}
          />
        </div>
      </div>

      <motion.button
        className={cn(
          "flex w-full items-center justify-center gap-2 rounded-xl border border-border-subtle px-4 py-3 text-sm text-text-secondary transition-colors",
          "hover:bg-surface-overlay hover:text-text-primary disabled:opacity-50"
        )}
        onClick={handlePreview}
        disabled={!selectedVoice || previewing}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.98 }}
      >
        {previewing ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
        Preview Voice
      </motion.button>

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="text-sm text-text-secondary">Drama</label>
            <span className="text-xs text-text-tertiary">{drama}</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={drama}
            onChange={(e) => setDrama(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="text-sm text-text-secondary">Pacing</label>
            <span className="text-xs text-text-tertiary">{pacing}</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={pacing}
            onChange={(e) => setPacing(Number(e.target.value))}
            className="w-full"
          />
        </div>
      </div>

      {audioReady && jobId ? (
        <audio
          src={`${API_BASE}/api/jobs/${jobId}/artifact/audio`}
          controls
          className="w-full"
        />
      ) : (
        <div className="rounded-lg border border-border-subtle bg-surface-raised px-4 py-3 text-xs text-text-secondary">
          Narration is being generated. The audio player will appear when it&apos;s ready.
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
          {awaitingStage === "narration" ? "Continue to render" : "Continue"}
        </motion.button>
      </div>
    </div>
  );
}
