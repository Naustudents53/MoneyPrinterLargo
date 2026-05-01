"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Eye, RotateCcw, ArrowRight, Image as ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface ImagesStageProps {
  onComplete?: () => void;
}

const SAMPLE_PROMPTS = [
  "Cinematic wide shot of an abandoned neon-lit library at midnight, rain on glass, cyberpunk palette",
  "Close-up of a glowing cassette tape resting on a rusty metal desk, soft volumetric lighting",
  "Aerial shot of a sprawling megacity at dusk, holographic ads reflecting off rooftops",
  "Silhouette of a hooded figure running through a steam-filled tunnel, red backlights",
  "Macro shot of crystalline data shards scattered on cracked concrete, purple and cyan glow",
  "Interior of a hidden server room, fiber-optic cables pulsing like bioluminescent vines",
];

export function ImagesStage({ onComplete }: ImagesStageProps) {
  const [prompts, setPrompts] = useState<string[]>(SAMPLE_PROMPTS);
  const [previewMap, setPreviewMap] = useState<Record<number, boolean>>({});

  const togglePreview = useCallback((index: number) => {
    setPreviewMap((prev) => ({ ...prev, [index]: !prev[index] }));
  }, []);

  const handleRegenerateAll = useCallback(() => {
    setPrompts((prev) =>
      prev.map((p, i) => `Regenerated prompt ${i + 1}: ${p.split(" ").slice(0, 6).join(" ")}...`)
    );
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-secondary">Image Prompts</h3>
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2 text-xs text-text-secondary transition-colors",
            "hover:bg-surface-overlay hover:text-text-primary"
          )}
          onClick={handleRegenerateAll}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
        >
          <RotateCcw size={14} />
          Regenerate All
        </motion.button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {prompts.map((prompt, index) => {
          const showPreview = previewMap[index];
          return (
            <motion.div
              key={index}
              className="flex flex-col gap-3 rounded-xl border border-border-ghost bg-surface-raised p-4 shadow-panel"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              {/* Prompt text */}
              <textarea
                className="w-full resize-none bg-transparent text-xs leading-relaxed text-text-primary outline-none"
                rows={3}
                value={prompt}
                onChange={(e) =>
                  setPrompts((prev) => prev.map((p, i) => (i === index ? e.target.value : p)))
                }
              />

              {/* Preview area */}
              {showPreview && (
                <motion.div
                  className="relative aspect-video w-full overflow-hidden rounded-lg"
                  style={{
                    background: "linear-gradient(135deg, #1E1E32, #0E0E18)",
                  }}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="flex h-full items-center justify-center text-text-muted">
                    <ImageIcon size={24} />
                  </div>
                </motion.div>
              )}

              {/* Actions */}
              <div className="flex justify-end">
                <motion.button
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg border border-border-subtle px-3 py-1.5 text-xs text-text-secondary transition-colors",
                    showPreview && "border-accent-purple/30 text-accent-purple-soft bg-accent-purple/5",
                    !showPreview && "hover:bg-surface-overlay hover:text-text-primary"
                  )}
                  onClick={() => togglePreview(index)}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Eye size={12} />
                  {showPreview ? "Hide" : "Preview"}
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
          Continue
          <ArrowRight size={16} />
        </motion.button>
      </div>
    </div>
  );
}
