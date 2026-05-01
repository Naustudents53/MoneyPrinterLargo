"use client";

import { motion } from "framer-motion";
import { Search, Plus, Activity } from "lucide-react";
import { useAgentStore } from "@/stores/agents";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { cn } from "@/lib/utils";

export function TopBar() {
  const { agents } = useAgentStore();
  const { openCommandPalette } = useUiStore();
  const { createProject } = useProjectStore();
  const activeAgents = agents.filter((a) => a.status === "working").length;

  return (
    <motion.header
      className="flex items-center h-14 px-5 gap-4 relative z-20"
      style={{
        background: "linear-gradient(180deg, rgba(8,8,15,0.95) 0%, rgba(8,8,15,0.6) 100%)",
        borderBottom: "1px solid rgba(30,30,50,0.6)",
      }}
    >
      {/* Barra de búsqueda como panel de control */}
      <motion.button
        className="flex items-center gap-3 flex-1 max-w-md h-9 rounded-lg px-3 text-sm transition-all"
        style={{
          background: "rgba(21,21,32,0.6)",
          border: "1px solid rgba(30,30,50,0.8)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)",
        }}
        onClick={openCommandPalette}
        whileHover={{
          borderColor: "rgba(124,58,237,0.3)",
          boxShadow: "0 0 20px rgba(124,58,237,0.08), inset 0 1px 0 rgba(255,255,255,0.03)",
        }}
      >
        <Search size={14} className="text-text-tertiary shrink-0" />
        <span className="flex-1 text-left text-text-tertiary text-[13px]">Search projects, commands...</span>
        <kbd className="hidden sm:inline-flex items-center rounded border border-border-default px-1.5 py-0.5 text-[10px] font-mono text-text-muted">
          <span className="text-xs">⌘</span>K
        </kbd>
      </motion.button>

      <div className="flex-1" />

      {/* Botón New Production */}
      <motion.button
        className="flex items-center gap-1.5 h-9 rounded-lg px-4 text-xs font-semibold tracking-wide text-white transition-colors"
        style={{
          background: "linear-gradient(135deg, #7C3AED, #5B21B6)",
          boxShadow: "0 0 20px rgba(124,58,237,0.25), inset 0 1px 0 rgba(255,255,255,0.1)",
          border: "1px solid rgba(124,58,237,0.4)",
        }}
        whileHover={{
          boxShadow: "0 0 30px rgba(124,58,237,0.4), inset 0 1px 0 rgba(255,255,255,0.15)",
          scale: 1.02,
        }}
        whileTap={{ scale: 0.98 }}
        onClick={() => createProject("New Production")}
      >
        <Plus size={14} />New Production
      </motion.button>

      {/* Indicador de agentes activos */}
      <motion.div
        className={cn(
          "flex items-center gap-2 h-7 rounded-full border px-3 text-[11px] font-mono tracking-wide",
          activeAgents > 0
            ? "border-accent-purple/20 bg-accent-purple/8 text-accent-purple-soft"
            : "border-border-ghost bg-surface-raised text-text-muted"
        )}
        whileHover={{ scale: 1.02 }}
      >
        <motion.div
          className="w-1.5 h-1.5 rounded-full"
          animate={{
            backgroundColor: activeAgents > 0 ? "#A78BFA" : "#3A3A55",
            scale: activeAgents > 0 ? [1, 1.4, 1] : 1,
            boxShadow: activeAgents > 0
              ? ["0 0 0px #7C3AED", "0 0 8px #7C3AED", "0 0 0px #7C3AED"]
              : "0 0 0px transparent",
          }}
          transition={activeAgents > 0 ? { duration: 2, repeat: Infinity } : {}}
        />
        {activeAgents > 0 ? `${activeAgents} active` : "idle"}
      </motion.div>

      {/* Estado de sistema */}
      <div className="hidden md:flex items-center gap-2">
        <div className="flex items-center gap-1.5 h-7 rounded-full border border-border-ghost bg-surface-raised px-3 text-[11px] font-mono text-text-muted">
          <Activity size={10} className="text-success" />
          GPU ready
        </div>
        <div className="flex items-center gap-1.5 h-7 rounded-full border border-border-ghost bg-surface-raised px-3 text-[11px] font-mono text-text-muted">
          Queue: 0
        </div>
      </div>

      {/* Avatar */}
      <motion.div
        className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white cursor-pointer relative overflow-hidden"
        style={{
          background: "linear-gradient(135deg, #7C3AED, #3B82F6)",
          boxShadow: "0 0 12px rgba(124,58,237,0.3)",
        }}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
      >
        DL
      </motion.div>
    </motion.header>
  );
}
