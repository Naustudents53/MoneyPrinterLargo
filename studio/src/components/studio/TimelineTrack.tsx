"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const TRACK_LABELS: Record<string, string> = { video: "Video", voice: "Voice", music: "Music", effects: "Effects" };

interface TimelineTrackProps { type: string; clips: { id: string; duration: number; startTime: number }[]; totalDuration: number; }

export function TimelineTrack({ type, clips, totalDuration }: TimelineTrackProps) {
  const colorMap: Record<string, string> = { video: "bg-blue-600/40 border-blue-400/60", voice: "bg-purple-600/40 border-purple-400/60", music: "bg-green-600/40 border-green-400/60", effects: "bg-orange-600/40 border-orange-400/60" };

  return (
    <div className="flex items-center gap-3 h-12 group">
      <div className="w-16 shrink-0 text-right"><span className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">{TRACK_LABELS[type] || type}</span></div>
      <motion.div className={cn("relative flex-1 h-8 rounded-lg border overflow-hidden", type === "video" ? "bg-blue-500/10 border-blue-500/20" : type === "voice" ? "bg-purple-500/10 border-purple-500/20" : type === "music" ? "bg-green-500/10 border-green-500/20" : "bg-orange-500/10 border-orange-500/20")} whileHover={{ scale: 1.01 }}>
        {clips.map((clip) => {
          const left = (clip.startTime / totalDuration) * 100;
          const width = (clip.duration / totalDuration) * 100;
          return (
            <motion.div key={clip.id} className={cn("absolute top-1 bottom-1 rounded-md border cursor-pointer", colorMap[type] || "bg-surface-raised border-border-subtle")} style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }} whileHover={{ scaleY: 1.2, zIndex: 10 }} layout>
              <div className="absolute inset-x-0 top-0 right-0 w-2 h-full opacity-0 group-hover:opacity-100 cursor-ew-resize bg-white/20 rounded-r-md" />
            </motion.div>
          );
        })}
        <motion.div className="absolute top-0 bottom-0 w-0.5 bg-white shadow-glow-purple z-20" animate={{ left: ["0%", "60%", "0%"] }} transition={{ duration: 6, repeat: Infinity, ease: "linear" }}>
          <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-3 h-3 bg-white rounded-sm rotate-45" />
        </motion.div>
      </motion.div>
    </div>
  );
}
