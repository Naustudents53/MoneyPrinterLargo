"use client";

import { motion } from "framer-motion";
import { Play, SkipBack, SkipForward, ZoomIn, ZoomOut, Scissors, Plus, Wand2 } from "lucide-react";
import { TimelineTrack as TimelineTrackComponent } from "@/components/studio/TimelineTrack";
import { useState } from "react";

const SAMPLE_TIMELINE = [
  { type: "video", clips: [{ id: "v1", duration: 30, startTime: 0 },{ id: "v2", duration: 40, startTime: 30 },{ id: "v3", duration: 25, startTime: 70 },{ id: "v4", duration: 35, startTime: 95 },{ id: "v5", duration: 45, startTime: 130 },{ id: "v6", duration: 30, startTime: 175 }] },
  { type: "voice", clips: [{ id: "a1", duration: 205, startTime: 0 }] },
  { type: "music", clips: [{ id: "m1", duration: 205, startTime: 0 }] },
  { type: "effects", clips: [{ id: "e1", duration: 5, startTime: 28 },{ id: "e2", duration: 5, startTime: 68 },{ id: "e3", duration: 8, startTime: 127 }] },
];

export function StageTimeline() {
  const [currentTime] = useState(65);
  const totalDuration = 205;
  const m = Math.floor(currentTime / 60), s = currentTime % 60;

  return (
    <motion.div className="h-full flex flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="flex items-center justify-between px-6 py-3" style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}>
        <div className="flex items-center gap-2">
          <motion.button
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
              color: "#9090B0",
            }}
            whileHover={{ borderColor: "rgba(232,162,79,0.2)", color: "#E8E8F0" }}
            whileTap={{ scale: 0.95 }}
          >
            <SkipBack size={14} />
          </motion.button>
          <motion.button
            className="w-10 h-10 rounded-xl flex items-center justify-center text-white transition-all"
            style={{
              background: "linear-gradient(135deg, #E8A24F, #C47A28)",
              boxShadow: "0 0 16px rgba(232,162,79,0.2), inset 0 1px 0 rgba(255,255,255,0.1)",
              border: "1px solid rgba(232,162,79,0.3)",
            }}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <Play size={18} className="ml-0.5" />
          </motion.button>
          <motion.button
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
              color: "#9090B0",
            }}
            whileHover={{ borderColor: "rgba(232,162,79,0.2)", color: "#E8E8F0" }}
            whileTap={{ scale: 0.95 }}
          >
            <SkipForward size={14} />
          </motion.button>
          <span className="text-sm font-mono text-text-primary ml-2">
            {String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}
          </span>
          <span className="text-sm font-mono text-text-muted">/ 03:25</span>
        </div>
        <div className="flex items-center gap-2">
          <motion.button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-secondary transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
            }}
            whileHover={{ borderColor: "rgba(30,30,50,0.8)" }}
          >
            <ZoomOut size={12} />
          </motion.button>
          <input type="range" min="0" max="100" defaultValue="50" className="w-20" />
          <motion.button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-secondary transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
            }}
            whileHover={{ borderColor: "rgba(30,30,50,0.8)" }}
          >
            <ZoomIn size={12} />
          </motion.button>
          <motion.button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-secondary transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
            }}
            whileHover={{ borderColor: "rgba(30,30,50,0.8)" }}
          >
            <Scissors size={12} />Split
          </motion.button>
          <motion.button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-secondary transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
            }}
            whileHover={{ borderColor: "rgba(30,30,50,0.8)" }}
          >
            <Wand2 size={12} />Auto-Edit
          </motion.button>
          <motion.button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-accent-purple-soft transition-all"
            style={{
              background: "rgba(232,162,79,0.06)",
              border: "1px solid rgba(232,162,79,0.15)",
            }}
            whileHover={{ background: "rgba(232,162,79,0.1)" }}
          >
            <Plus size={12} />Add Track
          </motion.button>
        </div>
      </div>

      <div className="flex items-center px-6 h-7" style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}>
        <div className="w-16 shrink-0" />
        <div className="flex-1 relative">
          {Array.from({ length: 9 }).map((_, i) => {
            const t = i * 30;
            const tm = Math.floor(t / 60), ts = t % 60;
            return (
              <span
                key={i}
                className="absolute -translate-x-1/2 text-[9px] font-mono"
                style={{ left: `${(t / totalDuration) * 100}%`, color: "#3A3A55" }}
              >
                {tm}:{String(ts).padStart(2, "0")}
              </span>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
        {SAMPLE_TIMELINE.map((track) => (
          <TimelineTrackComponent
            key={track.type}
            type={track.type}
            clips={track.clips}
            totalDuration={totalDuration}
          />
        ))}
      </div>

      <div className="flex items-center justify-between px-6 py-2 text-[10px] text-text-muted" style={{ borderTop: "1px solid rgba(30,30,50,0.5)" }}>
        <span>Track: infinity_cosmos.mp3</span>
        <span>3:25 total</span>
      </div>
    </motion.div>
  );
}
