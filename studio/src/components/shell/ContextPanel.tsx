"use client";

import { motion } from "framer-motion";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { X } from "lucide-react";

export function ContextPanel() {
  const { contextPanelOpen, toggleContextPanel } = useUiStore();
  const { projects, currentProjectId } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  if (!project) return null;

  return (
    <motion.aside className="relative flex flex-col h-full border-l border-border-subtle bg-surface-sunken/60 overflow-hidden" animate={{ width: contextPanelOpen ? 300 : 0, opacity: contextPanelOpen ? 1 : 0 }} transition={{ type: "spring", stiffness: 350, damping: 30 }}>
      <div className="flex items-center justify-between h-12 px-4 border-b border-border-subtle">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">Context</span>
        <button className="text-text-tertiary hover:text-text-primary transition-colors" onClick={toggleContextPanel}><X size={14} /></button>
      </div>
      <div className="flex-1 p-4 space-y-5 overflow-y-auto">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary mb-2">Production</div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between"><span className="text-text-tertiary">Movie</span><span className="text-text-primary">{project.movieTitle || "Not selected"}</span></div>
            <div className="flex justify-between"><span className="text-text-tertiary">Step</span><span className="font-mono text-accent-purple">{project.currentStep + 1} / 7</span></div>
            <div className="flex justify-between"><span className="text-text-tertiary">Scenes</span><span className="font-mono text-accent-blue">{project.scenes.length}</span></div>
            <div className="flex justify-between"><span className="text-text-tertiary">Clips</span><span className="font-mono text-accent-blue">{project.clips.length}</span></div>
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary mb-2">AI Reasoning</div>
          <p className="text-xs text-text-secondary leading-relaxed">{project.script ? "Script generated with three-pass analysis: plot beats → narration draft → pacing adjustment for target duration." : "Select a movie and proceed through analysis to unlock AI insights."}</p>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary mb-2">Quick Actions</div>
          <div className="space-y-1.5">
            {["Regenerate script", "Adjust pacing", "Change voice"].map((a) => (
              <motion.button key={a} className="flex items-center justify-between w-full px-3 py-2 rounded-lg border border-border-subtle bg-surface-raised hover:border-border-default transition-colors" whileHover={{ x: 2 }}>
                <span className="text-xs text-text-secondary">{a}</span>
              </motion.button>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary mb-2">Prompt Override</div>
          <textarea className="w-full h-16 rounded-lg bg-surface-raised border border-border-subtle text-xs text-text-secondary placeholder:text-text-tertiary px-3 py-2 resize-none focus:outline-none focus:border-accent-purple/50 transition-colors" placeholder="Custom instructions..." />
        </div>
      </div>
    </motion.aside>
  );
}
