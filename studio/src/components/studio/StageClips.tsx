"use client";

import { motion } from "framer-motion";
import { useProjectStore } from "@/stores/project";

export function StageClips() {
  const { projects, currentProjectId, setClips } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  const clips = project?.clips ?? [];

  return (
    <motion.div className="h-full flex flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="flex items-center justify-between px-6 py-3 border-b"
        style={{ borderColor: "rgba(30,30,50,0.5)" }}
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Extracted Clips ({clips.length})</span>
        <motion.button
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-accent-purple-soft transition-all"
          style={{
            background: "rgba(124,58,237,0.08)",
            border: "1px solid rgba(124,58,237,0.15)",
          }}
          whileHover={{ background: "rgba(124,58,237,0.15)" }}
          whileTap={{ scale: 0.97 }}
          onClick={() => setClips(SAMPLE_CLIPS)}
        >
          Regenerate All
        </motion.button>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {clips.map((clip, i) => (
            <motion.div
              key={clip.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <motion.div
                className="relative rounded-xl overflow-hidden group cursor-pointer aspect-video"
                style={{
                  background: "linear-gradient(135deg, #0E0E18, #08080F)",
                  border: "1px solid rgba(30,30,50,0.4)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)",
                }}
                whileHover={{
                  y: -4,
                  borderColor: "rgba(59,130,246,0.2)",
                  boxShadow: "0 0 20px rgba(59,130,246,0.08), inset 0 1px 0 rgba(255,255,255,0.03)",
                }}
                whileTap={{ scale: 0.98 }}
              >
                <div
                  className="absolute inset-0 flex items-center justify-center"
                  style={{
                    background: `linear-gradient(135deg, hsl(${250 + i * 5}, 60%, 10%), hsl(${250 + i * 5}, 30%, 4%))`,
                  }}
                >
                  <motion.div
                    className="w-10 h-10 rounded-full flex items-center justify-center"
                    style={{ background: "rgba(255,255,255,0.08)" }}
                    whileHover={{ scale: 1.1 }}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="white" opacity="0.7">
                      <polygon points="8 5, 19 12, 8 19" />
                    </svg>
                  </motion.div>
                </div>
                <div className="absolute top-0 inset-x-0 p-2 flex items-center justify-between">
                  <span
                    className="text-[10px] font-mono text-white/60 px-1.5 py-0.5 rounded-md"
                    style={{ background: "rgba(0,0,0,0.5)" }}
                  >
                    {clip.startTime}s
                  </span>
                </div>
                <div
                  className="absolute bottom-0 inset-x-0 p-2"
                  style={{
                    background: "linear-gradient(to top, rgba(2,2,5,0.9), transparent)",
                  }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <div className="flex-1 h-1 rounded-full overflow-hidden"
                      style={{ background: "rgba(255,255,255,0.08)" }}
                    >
                      <motion.div
                        className="h-full rounded-full"
                        style={{
                          width: `${clip.confidence * 100}%`,
                          background: clip.confidence > 0.9
                            ? "#10B981"
                            : clip.confidence > 0.85
                            ? "#F59E0B"
                            : "#EF4444",
                        }}
                        initial={{ width: 0 }}
                        animate={{ width: `${clip.confidence * 100}%` }}
                        transition={{ duration: 0.5, delay: i * 0.05 }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-white/70">
                      {Math.round(clip.confidence * 100)}%
                    </span>
                  </div>
                  <p className="text-[10px] text-white/50 truncate">{clip.reason}</p>
                </div>
              </motion.div>
            </motion.div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

import { MovieClip } from "@/stores/project";

const SAMPLE_CLIPS: MovieClip[] = [
  { id: "1", startTime: 0, endTime: 30, confidence: 0.97, reason: "Iconic establishing shot" },
  { id: "2", startTime: 134, endTime: 174, confidence: 0.92, reason: "High contrast, dramatic" },
  { id: "3", startTime: 268, endTime: 298, confidence: 0.95, reason: "Character close-up" },
  { id: "4", startTime: 405, endTime: 445, confidence: 0.88, reason: "Action sequence" },
  { id: "5", startTime: 560, endTime: 600, confidence: 0.94, reason: "Visual effects peak" },
  { id: "6", startTime: 694, endTime: 724, confidence: 0.89, reason: "Emotional climax" },
  { id: "7", startTime: 841, endTime: 881, confidence: 0.93, reason: "Gothic cinematography" },
  { id: "8", startTime: 980, endTime: 1020, confidence: 0.91, reason: "Flood sequence" },
  { id: "9", startTime: 1040, endTime: 1070, confidence: 0.96, reason: "Robot reveal" },
  { id: "10", startTime: 1104, endTime: 1134, confidence: 0.87, reason: "Chase on rooftop" },
  { id: "11", startTime: 1180, endTime: 1210, confidence: 0.90, reason: "Cathedral finale" },
  { id: "12", startTime: 1250, endTime: 1280, confidence: 0.86, reason: "Closing meditation" },
];
