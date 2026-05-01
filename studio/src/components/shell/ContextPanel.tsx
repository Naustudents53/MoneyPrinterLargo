"use client";

import { motion } from "framer-motion";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { X, Zap, Clock, Layers, Wand2 } from "lucide-react";

export function ContextPanel() {
  const { contextPanelOpen, toggleContextPanel } = useUiStore();
  const { projects, currentProjectId } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  if (!project) return null;

  return (
    <motion.aside
      className="relative flex flex-col h-full overflow-hidden z-10"
      style={{
        background: "linear-gradient(180deg, rgba(6,6,16,0.8) 0%, rgba(8,8,15,0.6) 100%)",
        borderLeft: "1px solid rgba(30,30,50,0.5)",
      }}
      animate={{ width: contextPanelOpen ? 280 : 0, opacity: contextPanelOpen ? 1 : 0 }}
      transition={{ type: "spring", stiffness: 350, damping: 30 }}
    >
      <div className="flex items-center justify-between h-12 px-4 border-b border-border-ghost">
        <div className="flex items-center gap-2">
          <Zap size={12} className="text-accent-purple-soft" />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Mission Control</span>
        </div>
        <button
          className="text-text-muted hover:text-text-primary transition-colors"
          onClick={toggleContextPanel}
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 p-4 space-y-6 overflow-y-auto">
        {/* Estado de producción */}
        <div
          className="rounded-xl p-3 space-y-3"
          style={{
            background: "rgba(124,58,237,0.04)",
            border: "1px solid rgba(124,58,237,0.1)",
          }}
        >
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2">
            Production Status
          </div>
          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-text-tertiary flex items-center gap-1.5">
                <Layers size={10} /> Movie
              </span>
              <span className="text-text-primary font-medium truncate max-w-[120px]">
                {project.movieTitle || "Not selected"}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-text-tertiary flex items-center gap-1.5">
                <Clock size={10} /> Step
              </span>
              <span className="font-mono text-accent-purple-soft">
                {project.currentStep + 1} / 7
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-text-tertiary">Scenes</span>
              <span className="font-mono text-accent-blue-soft">{project.scenes.length}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-text-tertiary">Clips</span>
              <span className="font-mono text-accent-blue-soft">{project.clips.length}</span>
            </div>
          </div>

          {/* Barra de progreso */}
          <div className="mt-3">
            <div className="h-1 rounded-full overflow-hidden bg-surface-sunken">
              <motion.div
                className="h-full rounded-full"
                style={{
                  background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
                  boxShadow: "0 0 8px rgba(124,58,237,0.3)",
                }}
                initial={{ width: 0 }}
                animate={{ width: `${((project.currentStep + 1) / 7) * 100}%` }}
                transition={{ duration: 0.8, ease: "easeOut" }}
              />
            </div>
          </div>
        </div>

        {/* AI Reasoning */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2">
            AI Reasoning
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">
            {project.script
              ? "Script generated with three-pass analysis: plot beats → narration draft → pacing adjustment for target duration."
              : "Select a movie and proceed through analysis to unlock AI insights."}
          </p>
        </div>

        {/* Quick Actions */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2">
            Quick Actions
          </div>
          <div className="space-y-1.5">
            {["Regenerate script", "Adjust pacing", "Change voice"].map((a) => (
              <motion.button
                key={a}
                className="flex items-center justify-between w-full px-3 py-2 rounded-lg text-xs text-text-secondary transition-all group"
                style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(30,30,50,0.5)",
                }}
                whileHover={{
                  x: 2,
                  borderColor: "rgba(124,58,237,0.2)",
                  background: "rgba(124,58,237,0.04)",
                }}
              >
                <span className="flex items-center gap-2">
                  <Wand2 size={10} className="text-text-muted group-hover:text-accent-purple-soft transition-colors" />
                  {a}
                </span>
              </motion.button>
            ))}
          </div>
        </div>

        {/* Prompt Override */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2">
            Prompt Override
          </div>
          <textarea
            className="w-full h-20 rounded-lg text-xs text-text-secondary placeholder:text-text-muted px-3 py-2 resize-none focus:outline-none transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
            }}
            placeholder="Custom instructions..."
          />
        </div>
      </div>
    </motion.aside>
  );
}
