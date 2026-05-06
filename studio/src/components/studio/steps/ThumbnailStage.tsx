"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, ChevronDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useProductionStore } from "@/stores/production";
import { useJobEvents } from "@/lib/useJobEvents";
import {
  API_BASE,
  continueJob,
  getGateStatus,
  type Stage,
} from "@/lib/api";

interface ThumbnailStageProps {
  onComplete?: () => void;
}

const FONTS = [
  { label: "Bold", value: "bold_font" },
  { label: "Poppins Black", value: "Poppins-Black" },
  { label: "Montserrat ExtraBold", value: "Montserrat-ExtraBold" },
];

const THEMES = ["dark", "cosmic", "war", "neon"];

const THEME_GRADIENTS: Record<string, string> = {
  dark: "linear-gradient(135deg, #0E0E18, #1C1C2B)",
  cosmic: "linear-gradient(135deg, #1a0b2e, #2d1b69)",
  war: "linear-gradient(135deg, #1a0a0a, #3d1f1f)",
  neon: "linear-gradient(135deg, #0a1a0a, #1f3d3f)",
};

// 3 variant decks — each card gets its own gradient + label
const VARIANT_DECKS = [
  {
    label: "A",
    badge: "variant-a",
    bg: "linear-gradient(135deg, #0E0E18, #2d1b69)", // dark + cosmic
    accent: "#A78BFA",
  },
  {
    label: "B",
    badge: "variant-b",
    bg: "linear-gradient(135deg, #1a0a0a, #3d1f1f)", // war red
    accent: "#F87171",
  },
  {
    label: "C",
    badge: "variant-c",
    bg: "linear-gradient(135deg, #0a1a0a, #1f3d3f)", // neon green
    accent: "#67E8F9",
  },
];

export function ThumbnailStage({ onComplete }: ThumbnailStageProps) {
  const [title, setTitle] = useState("NEON ARCHIVES");
  const [overlay, setOverlay] = useState("Episode 1");
  const [font, setFont] = useState(FONTS[0].value);
  const [theme, setTheme] = useState("dark");
  const [thumbnailReady, setThumbnailReady] = useState(false);
  const [awaitingStage, setAwaitingStage] = useState<Stage | null>(null);
  const [resuming, setResuming] = useState(false);
  const [cacheBuster, setCacheBuster] = useState(0);

  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const jobId = production?.jobId;

  // Hydrate gate state on mount in case the awaiting event already fired.
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    getGateStatus(jobId)
      .then(({ awaiting }) => {
        if (!cancelled) {
          setAwaitingStage(awaiting);
          // If we're already paused at the thumbnail gate, the thumbnail was
          // generated earlier and the stage.done event was missed. Force ready
          // so the real image renders instead of the placeholder text.
          if (awaiting === "thumbnail") {
            setThumbnailReady(true);
            setCacheBuster(Date.now());
          }
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useJobEvents(jobId ?? null, {
    "stage.done": (e) => {
      if (e.stage === "thumbnail") {
        setThumbnailReady(true);
        setCacheBuster(Date.now());
      }
    },
    "stage.awaiting": (e) => setAwaitingStage(e.stage),
    "stage.resumed": (e) => {
      if (e.stage === awaitingStage) setAwaitingStage(null);
    },
  });

  const handleContinue = async () => {
    if (!jobId) {
      onComplete?.();
      return;
    }
    if (awaitingStage !== "thumbnail") {
      onComplete?.();
      return;
    }
    setResuming(true);
    try {
      // Thumbnail edits are advisory for now (the rendered thumbnail PNG
      // already exists on disk). The runner doesn't re-render — it just
      // releases the gate so TTS+render can proceed.
      await continueJob(jobId, "thumbnail", { title, overlay, font, theme });
      onComplete?.();
    } finally {
      setResuming(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      {awaitingStage === "thumbnail" && (
        <div className="flex justify-end">
          <span className="rounded-full border border-accent-purple/30 bg-accent-purple/10 px-3 py-1 text-[11px] text-accent-purple-soft">
            Review thumbnail before TTS
          </span>
        </div>
      )}

      {/* Preview — 3 variant thumbnail cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {VARIANT_DECKS.map((deck, i) => (
          <motion.div
            key={deck.label}
            className="group relative aspect-video overflow-hidden rounded-2xl border-2 border-transparent bg-surface-raised shadow-panel transition-colors hover:border-white/10"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            {/* Glow ring on hover */}
            <div
              className="pointer-events-none absolute -inset-[1px] rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
              style={{
                background: `linear-gradient(135deg, ${deck.accent}20, transparent 60%)`,
              }}
            />

            {/* Variant badge */}
            <div
              className="absolute left-3 top-3 z-10 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-black backdrop-blur-sm"
              style={{ background: deck.accent }}
            >
              {deck.label}
            </div>

            {thumbnailReady && jobId ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`${API_BASE}/api/jobs/${jobId}/artifact/thumbnail?t=${cacheBuster}`}
                alt={`Thumbnail variant ${deck.label}`}
                className="h-full w-full object-cover rounded-2xl"
              />
            ) : (
              <div
                className="flex h-full w-full flex-col items-center justify-center gap-2 p-5"
                style={{ background: deck.bg }}
              >
                <span
                  className="text-center text-lg font-extrabold text-white/90 drop-shadow-lg md:text-xl"
                  style={{
                    fontFamily:
                      font === "bold_font"
                        ? "bold_font"
                        : font === "Poppins-Black"
                          ? "Poppins"
                          : "Montserrat",
                  }}
                >
                  {title}
                </span>
                <span className="text-[11px] font-medium text-white/60">{overlay}</span>
              </div>
            )}
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <label className="text-sm text-text-secondary">Title</label>
          <input
            className="rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm text-text-secondary">Overlay Text</label>
          <input
            className="rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={overlay}
            onChange={(e) => setOverlay(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm text-text-secondary">Font</label>
          <div className="relative">
            <select
              className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
              value={font}
              onChange={(e) => setFont(e.target.value)}
            >
              {FONTS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <ChevronDown
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
              size={16}
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm text-text-secondary">Color Theme</label>
          <div className="relative">
            <select
              className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
            >
              {THEMES.map((t) => (
                <option key={t} value={t}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
            <ChevronDown
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
              size={16}
            />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end pt-2">
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
          {awaitingStage === "thumbnail" ? "Continue to narration" : "Continue"}
        </motion.button>
      </div>
    </div>
  );
}
