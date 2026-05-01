"use client";

import { motion } from "framer-motion";
import { Film, Clock, HardDrive } from "lucide-react";

interface RenderProgressProps { progress: number; eta: string; fileSizeEstimate: string; currentOperation: string; }

export function RenderProgress({ progress, eta, fileSizeEstimate, currentOperation }: RenderProgressProps) {
  return (
    <motion.div className="w-full max-w-md bg-surface-overlay border border-border-default rounded-2xl p-6 space-y-5" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}>
      <div className="flex items-center gap-3">
        <motion.div animate={{ rotate: 360 }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }}><Film size={20} className="text-accent-purple" /></motion.div>
        <div><div className="text-sm font-medium text-text-primary">Rendering</div><div className="text-xs text-text-tertiary">{currentOperation}</div></div>
        <motion.span className="ml-auto text-2xl font-bold font-mono text-accent-purple" animate={{ opacity: [0.6, 1, 0.6] }} transition={{ duration: 2, repeat: Infinity }}>{progress}%</motion.span>
      </div>
      <div className="relative h-2.5 bg-surface-sunken rounded-full overflow-hidden">
        <motion.div className="absolute inset-y-0 left-0 rounded-full" style={{ background: "linear-gradient(90deg, #7C3AED, #3B82F6, #8B5CF6)", backgroundSize: "200% 100%", width: `${progress}%` }} animate={{ backgroundPosition: ["0% 0%", "100% 0%", "0% 0%"] }} transition={{ duration: 3, repeat: Infinity }} />
        <motion.div className="absolute inset-y-0 w-16" style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)" }} animate={{ x: ["-100%", "600%"] }} transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }} />
      </div>
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-text-tertiary flex items-center gap-1.5"><Clock size={12} />{eta}</span>
        <span className="text-text-tertiary flex items-center gap-1.5"><HardDrive size={12} />~{fileSizeEstimate}</span>
      </div>
    </motion.div>
  );
}
