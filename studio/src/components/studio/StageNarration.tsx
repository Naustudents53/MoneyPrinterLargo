"use client";

import { motion } from "framer-motion";
import { Mic, Play, Pause, Volume2, Sparkles } from "lucide-react";
import { useProjectStore } from "@/stores/project";
import { useState } from "react";

const VOICES = [
  { id: "es-1", name: "Alejandro", description: "Deep baritone, dramatic pacing", gender: "male" as const },
  { id: "es-2", name: "Catalina", description: "Smooth alto, neutral tone", gender: "female" as const },
  { id: "es-3", name: "Mateo", description: "Warm tenor, storytelling cadence", gender: "male" as const },
  { id: "en-1", name: "Arthur", description: "British narrator, authoritative", gender: "male" as const },
];

export function StageNarration() {
  const { projects, currentProjectId } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  const script = project?.script || "";
  const [selectedVoice, setSelectedVoice] = useState(VOICES[0].id);
  const [playing, setPlaying] = useState(false);
  const [dramaLevel, setDramaLevel] = useState(70);
  const [pace, setPace] = useState(50);

  return (
    <motion.div className="h-full flex" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="w-[320px] flex flex-col"
        style={{
          borderRight: "1px solid rgba(30,30,50,0.5)",
          background: "linear-gradient(180deg, rgba(6,6,16,0.5), rgba(8,8,15,0.3))",
        }}
      >
        <div className="px-4 py-3" style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}>
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Voice Profile</span>
        </div>
        <div className="flex-1 p-3 space-y-2">
          {VOICES.map((voice) => (
            <motion.button
              key={voice.id}
              className="flex items-start gap-3 w-full p-3 rounded-xl text-left transition-all"
              style={
                selectedVoice === voice.id
                  ? {
                      background: "rgba(124,58,237,0.06)",
                      border: "1px solid rgba(124,58,237,0.15)",
                    }
                  : {
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.4)",
                    }
              }
              whileHover={{
                x: 3,
                borderColor: "rgba(124,58,237,0.15)",
              }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setSelectedVoice(voice.id)}
            >
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                style={
                  voice.gender === "male"
                    ? {
                        background: "rgba(59,130,246,0.08)",
                        color: "#60A5FA",
                      }
                    : {
                        background: "rgba(124,58,237,0.08)",
                        color: "#A78BFA",
                      }
                }
              >
                <Mic size={16} />
              </div>
              <div>
                <div className="text-sm font-medium text-text-primary">{voice.name}</div>
                <div className="text-[11px] text-text-muted">{voice.description}</div>
              </div>
            </motion.button>
          ))}
        </div>
        <div className="p-4 space-y-4" style={{ borderTop: "1px solid rgba(30,30,50,0.5)" }}>
          <div>
            <div className="flex justify-between mb-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Drama</span>
              <span className="text-[10px] font-mono" style={{ color: "#A78BFA" }}>{dramaLevel}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={dramaLevel}
              onChange={(e) => setDramaLevel(Number(e.target.value))}
            />
          </div>
          <div>
            <div className="flex justify-between mb-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Pacing</span>
              <span className="text-[10px] font-mono" style={{ color: "#60A5FA" }}>{pace}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={pace}
              onChange={(e) => setPace(Number(e.target.value))}
            />
          </div>
          <motion.button
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-white text-sm font-medium transition-all"
            style={{
              background: "linear-gradient(135deg, #7C3AED, #5B21B6)",
              boxShadow: "0 0 20px rgba(124,58,237,0.2), inset 0 1px 0 rgba(255,255,255,0.1)",
              border: "1px solid rgba(124,58,237,0.3)",
            }}
            whileHover={{
              scale: 1.02,
              boxShadow: "0 0 30px rgba(124,58,237,0.3), inset 0 1px 0 rgba(255,255,255,0.15)",
            }}
            whileTap={{ scale: 0.98 }}
          >
            <Sparkles size={14} /> Generate Narration
          </motion.button>
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between px-6 py-3" style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}>
          <div className="flex items-center gap-3">
            <motion.button
              className="flex items-center justify-center w-9 h-9 rounded-xl transition-all"
              style={
                playing
                  ? {
                      background: "linear-gradient(135deg, #7C3AED, #5B21B6)",
                      boxShadow: "0 0 12px rgba(124,58,237,0.3)",
                      color: "#fff",
                    }
                  : {
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.5)",
                      color: "#9090B0",
                    }
              }
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setPlaying(!playing)}
            >
              {playing ? <Pause size={16} /> : <Play size={16} className="ml-0.5" />}
            </motion.button>
            <div>
              <div className="text-sm font-medium text-text-primary">Alejandro — Deep baritone</div>
              <div className="text-[10px] text-text-muted">15:24 total duration</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Volume2 size={14} className="text-text-muted" />
            <div className="w-24 h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.04)" }}>
              <motion.div
                className="h-full rounded-full"
                style={{
                  background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
                  boxShadow: "0 0 8px rgba(124,58,237,0.3)",
                }}
                animate={{ width: playing ? "75%" : "0%" }}
              />
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-2xl mx-auto text-sm leading-relaxed space-y-4 font-mono">
            {script.split("\n\n").map((para, i) => (
              <motion.p
                key={i}
                className="rounded-lg px-2 py-1 -mx-2 transition-colors"
                style={{ color: "#9090B0" }}
                whileHover={{
                  background: "rgba(124,58,237,0.04)",
                  color: "#E8E8F0",
                }}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <span className={playing && i === 2 ? "font-medium" : ""}
                  style={playing && i === 2 ? { color: "#A78BFA" } : {}}
                >
                  {para}
                </span>
              </motion.p>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
