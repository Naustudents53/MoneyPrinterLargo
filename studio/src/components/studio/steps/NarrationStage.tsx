"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Play, ArrowRight, Loader2, Volume2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface NarrationStageProps {
  onComplete?: () => void;
}

interface VoiceItem {
  id: string;
  alias: string;
}

export function NarrationStage({ onComplete }: NarrationStageProps) {
  const [voices, setVoices] = useState<VoiceItem[]>([]);
  const [selectedVoice, setSelectedVoice] = useState("");
  const [drama, setDrama] = useState(50);
  const [pacing, setPacing] = useState(50);
  const [previewing, setPreviewing] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/api/config/voices")
      .then((r) => r.ok ? r.json() : [])
      .then((data: VoiceItem[]) => setVoices(data))
      .catch(() => setVoices([]));
  }, []);

  const handlePreview = useCallback(async () => {
    if (!selectedVoice) return;
    try {
      setPreviewing(true);
      await fetch("http://localhost:8000/api/tts/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice: selectedVoice, text: "This is a preview of the selected voice." }),
      });
    } catch {
      // noop
    } finally {
      setPreviewing(false);
    }
  }, [selectedVoice]);

  const handleGenerateFull = useCallback(async () => {
    try {
      setGenerating(true);
      await new Promise((resolve) => setTimeout(resolve, 1500));
      // Hook for real full generation later
    } finally {
      setGenerating(false);
    }
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Voice selector */}
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
              <option key={v.id} value={v.id}>{v.alias}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
        </div>
      </div>

      {/* Preview voice */}
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

      {/* Sliders */}
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

      {/* Generate full narration */}
      <motion.button
        className={cn(
          "flex items-center justify-center gap-2 rounded-xl bg-accent-purple px-4 py-3 text-sm font-medium text-white shadow-glow-purple transition-colors",
          "hover:bg-accent-purple-deep disabled:opacity-50"
        )}
        onClick={handleGenerateFull}
        disabled={generating}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.97 }}
      >
        {generating ? <Loader2 size={16} className="animate-spin" /> : <Volume2 size={16} />}
        Generate Full Narration
      </motion.button>

      {/* Audio player placeholder */}
      <div className="flex items-center gap-3 rounded-xl border border-border-ghost bg-surface-raised p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-overlay text-text-muted">
          <Play size={14} />
        </div>
        <div className="flex flex-1 flex-col gap-1.5">
          <div className="h-1.5 w-full rounded bg-surface-sunken">
            <div className="h-full w-0 rounded bg-accent-purple" />
          </div>
          <div className="flex justify-between text-[10px] text-text-muted">
            <span>00:00</span>
            <span>00:00</span>
          </div>
        </div>
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
          Continue
          <ArrowRight size={16} />
        </motion.button>
      </div>
    </div>
  );
}
