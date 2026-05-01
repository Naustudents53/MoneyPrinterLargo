"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Wand2, ArrowRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

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

export function ThumbnailStage({ onComplete }: ThumbnailStageProps) {
  const [title, setTitle] = useState("NEON ARCHIVES");
  const [overlay, setOverlay] = useState("Episode 1");
  const [font, setFont] = useState(FONTS[0].value);
  const [theme, setTheme] = useState("dark");

  const handleGenerate = useCallback(() => {
    // Hook for API call later
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Preview */}
      <motion.div
        className="relative aspect-video w-full overflow-hidden rounded-2xl border border-border-ghost shadow-float"
        style={{ background: THEME_GRADIENTS[theme] }}
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
      >
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6">
          <span
            className="text-center text-3xl font-extrabold text-text-primary drop-shadow-lg md:text-5xl"
            style={{ fontFamily: font === "bold_font" ? "bold_font" : font === "Poppins-Black" ? "Poppins" : "Montserrat" }}
          >
            {title}
          </span>
          <span className="text-sm font-medium text-text-secondary">{overlay}</span>
        </div>
        <div className="scanline pointer-events-none absolute inset-0" />
      </motion.div>

      {/* Controls */}
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
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
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
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2">
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl bg-accent-purple px-4 py-2.5 text-sm font-medium text-white shadow-glow-purple transition-colors",
            "hover:bg-accent-purple-deep"
          )}
          onClick={handleGenerate}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          <Wand2 size={16} />
          Generate
        </motion.button>

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
