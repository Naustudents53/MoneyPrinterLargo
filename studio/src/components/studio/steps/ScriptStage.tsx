"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Wand2, RotateCcw, ArrowRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface ScriptStageProps {
  onComplete?: () => void;
}

const FALLBACK_SCRIPT = [
  "In a world where silence is the only currency, one voice refuses to be quiet.",
  "Meet Elara, an archivist who stumbled upon a frequency that rewires memory itself.",
  "When the regime discovers her secret, the chase begins through collapsed archives and neon alleys.",
  "Will she broadcast the signal, or will the silence finally win?",
];

export function ScriptStage({ onComplete }: ScriptStageProps) {
  const [script, setScript] = useState<string[]>(FALLBACK_SCRIPT);
  const [generating, setGenerating] = useState(false);
  const [topic, setTopic] = useState("Neon Archives");

  const handleGenerate = useCallback(async () => {
    try {
      setGenerating(true);
      const res = await fetch("http://localhost:8000/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "short", topic }),
      });
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      if (Array.isArray(data.script)) setScript(data.script);
      else if (typeof data.script === "string") setScript([data.script]);
    } catch {
      // Fallback already present
    } finally {
      setGenerating(false);
    }
  }, [topic]);

  const handleRegenerateParagraph = useCallback(
    async (index: number) => {
      try {
        // In production: call API for single paragraph regeneration
        const fresh = `Regenerated paragraph ${index + 1} from the neon archives story line.`;
        setScript((prev) => prev.map((p, i) => (i === index ? fresh : p)));
      } catch {
        // noop
      }
    },
    []
  );

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <input
          className="flex-1 rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
          placeholder="Topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl bg-accent-purple px-4 py-3 text-sm font-medium text-white shadow-glow-purple transition-colors",
            "hover:bg-accent-purple-deep disabled:opacity-50"
          )}
          onClick={handleGenerate}
          disabled={generating}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          {generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
          Generate Script
        </motion.button>
      </div>

      <div className="flex flex-col gap-4">
        {script.map((paragraph, index) => (
          <motion.div
            key={index}
            className="rounded-xl border border-border-ghost bg-surface-raised p-4 shadow-panel"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06 }}
          >
            <textarea
              className="w-full resize-none bg-transparent text-sm leading-relaxed text-text-primary outline-none"
              rows={2}
              value={paragraph}
              onChange={(e) =>
                setScript((prev) => prev.map((p, i) => (i === index ? e.target.value : p)))
              }
            />
            <div className="mt-2 flex justify-end">
              <motion.button
                className="flex items-center gap-1.5 rounded-lg border border-border-subtle px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface-overlay hover:text-text-primary"
                onClick={() => handleRegenerateParagraph(index)}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
              >
                <RotateCcw size={12} />
                Regenerate
              </motion.button>
            </div>
          </motion.div>
        ))}
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
