"use client";

import { motion } from "framer-motion";
import { Film, Monitor, Smartphone, Download, Video, Sparkles, Check } from "lucide-react";
import { useProjectStore } from "@/stores/project";
import { RenderProgress } from "@/components/studio/RenderProgress";
import { useState } from "react";

const PLATFORMS = [
  { id: "youtube", label: "YouTube", icon: <Video size={20} />, aspect: "16:9", res: "1920 × 1080" },
  { id: "youtube-shorts", label: "YouTube Shorts", icon: <Smartphone size={20} />, aspect: "9:16", res: "1080 × 1920" },
  { id: "tiktok", label: "TikTok", icon: <Monitor size={20} />, aspect: "9:16", res: "1080 × 1920" },
];

export function StageExport({ onComplete }: { onComplete?: () => void }) {
  const { projects, currentProjectId, updateExportSettings } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  const exportSettings = project?.exportSettings ?? { resolution: "1080p" as const, format: "mp4" as const, platform: "youtube" as const };
  const [rendering, setRendering] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  const startRender = () => {
    setRendering(true);
    setProgress(0);
    setDone(false);
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          clearInterval(interval);
          setDone(true);
          setRendering(false);
          onComplete?.();
          return 100;
        }
        return p + Math.random() * 8;
      });
    }, 500);
  };

  return (
    <motion.div className="h-full flex" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-6">
        <motion.div
          className="relative w-full max-w-xl aspect-video rounded-2xl overflow-hidden"
          style={{
            border: "1px solid rgba(30,30,50,0.5)",
            background: "linear-gradient(135deg, #08080F, #06060A)",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02), 0 16px 48px rgba(0,0,0,0.5)",
          }}
          whileHover={{ scale: 1.01 }}
        >
          <div
            className="absolute inset-0"
            style={{
              background: "linear-gradient(135deg, rgba(124,58,237,0.06), transparent, rgba(59,130,246,0.04))",
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Film size={48} className="mx-auto mb-2" style={{ color: "rgba(124,58,237,0.25)" }} />
              <span className="text-sm text-text-muted">Metropolis — AI Recap</span>
            </div>
          </div>

          {done && (
            <motion.div
              className="absolute inset-0 flex items-center justify-center"
              style={{ background: "rgba(0,0,0,0.5)" }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center"
                style={{
                  background: "rgba(16,185,129,0.1)",
                  border: "1px solid rgba(16,185,129,0.3)",
                }}
              >
                <Check size={28} style={{ color: "#10B981" }} />
              </div>
            </motion.div>
          )}
        </motion.div>

        <div className="flex items-center gap-3">
          {PLATFORMS.map((p) => (
            <motion.button
              key={p.id}
              className="flex flex-col items-center gap-1.5 px-5 py-3 rounded-xl border transition-all"
              style={
                exportSettings.platform === p.id
                  ? {
                      background: "rgba(124,58,237,0.06)",
                      border: "1px solid rgba(124,58,237,0.2)",
                      color: "#A78BFA",
                    }
                  : {
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.5)",
                      color: "#5A5A7A",
                    }
              }
              whileHover={{
                y: -2,
                borderColor: exportSettings.platform === p.id ? "rgba(124,58,237,0.35)" : "rgba(30,30,50,0.8)",
              }}
              whileTap={{ scale: 0.97 }}
              onClick={() => updateExportSettings({ platform: p.id as typeof exportSettings.platform })}
            >
              {p.icon}
              <span className="text-[10px] font-medium">{p.label}</span>
              <span className="text-[9px] text-text-muted">{p.aspect} · {p.res}</span>
            </motion.button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mr-2">Res</span>
          {(["1080p", "720p", "480p"] as const).map((r) => (
            <motion.button
              key={r}
              className="px-3 py-1.5 rounded-lg text-xs font-mono transition-all"
              style={
                exportSettings.resolution === r
                  ? {
                      background: "rgba(124,58,237,0.08)",
                      color: "#A78BFA",
                      border: "1px solid rgba(124,58,237,0.2)",
                    }
                  : {
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.5)",
                      color: "#5A5A7A",
                    }
              }
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => updateExportSettings({ resolution: r })}
            >
              {r}
            </motion.button>
          ))}
        </div>
      </div>

      <div
        className="w-[340px] flex flex-col items-center justify-center p-6"
        style={{
          borderLeft: "1px solid rgba(30,30,50,0.5)",
          background: "linear-gradient(180deg, rgba(6,6,16,0.5), rgba(8,8,15,0.3))",
        }}
      >
        {rendering || done ? (
          <RenderProgress
            progress={Math.min(Math.round(progress), 100)}
            eta={done ? "Done" : `~${Math.ceil((100 - progress) / 15)}s`}
            fileSizeEstimate={exportSettings.resolution === "1080p" ? "850 MB" : "480 MB"}
            currentOperation={
              done
                ? "Export complete"
                : progress < 40
                ? "Encoding video..."
                : progress < 70
                ? "Mixing audio..."
                : "Writing file..."
            }
          />
        ) : (
          <div className="text-center">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
              style={{
                background: "rgba(124,58,237,0.06)",
                border: "1px solid rgba(124,58,237,0.15)",
              }}
            >
              <Sparkles size={28} style={{ color: "rgba(167,139,250,0.6)" }} />
            </div>
            <h3 className="text-base font-semibold text-text-primary mb-1">Ready to Export</h3>
            <p className="text-xs text-text-muted mb-6">Metropolis Recap · ~15 min · 1080p MP4</p>
            <motion.button
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-white text-sm font-medium transition-all mb-3"
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
              onClick={startRender}
            >
              <Download size={16} />Export Video
            </motion.button>
            <button
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm transition-all"
              style={{
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(30,30,50,0.5)",
                color: "#9090B0",
              }}
            >
              <Video size={16} />Export & Upload
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
