"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface AIThinkingIndicatorProps { label?: string; variant?: "inline" | "card" | "minimal"; className?: string; }

export function AIThinkingIndicator({ label = "AI is thinking", variant = "inline", className }: AIThinkingIndicatorProps) {
  if (variant === "minimal") {
    return (
      <motion.span className={cn("inline-flex gap-0.5", className)}>
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="w-1.5 h-1.5 rounded-full bg-accent-purple" animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }} transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }} />
        ))}
      </motion.span>
    );
  }

  if (variant === "card") {
    return (
      <motion.div className={cn("flex items-center gap-3 px-4 py-3 rounded-xl bg-surface-overlay border border-border-subtle", className)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
        <motion.div animate={{ rotate: 360 }} transition={{ duration: 3, repeat: Infinity, ease: "linear" }}><Sparkles size={18} className="text-accent-purple" /></motion.div>
        <span className="text-sm text-text-secondary">{label}</span>
      </motion.div>
    );
  }

  return (
    <motion.div className={cn("flex items-center gap-2", className)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="w-4 h-4 rounded-full border-2 border-accent-purple/30 border-t-accent-purple animate-spin" />
      <span className="text-xs text-text-tertiary">{label}</span>
    </motion.div>
  );
}
