"use client";

import { motion } from "framer-motion";
import { Search, Circle, Plus } from "lucide-react";
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
    <header className="flex items-center h-14 px-4 gap-3 border-b border-border-subtle bg-surface-base/80 backdrop-blur-sm">
      <motion.button className="flex items-center gap-2 flex-1 max-w-md h-8 rounded-lg bg-surface-raised border border-border-subtle px-3 text-sm text-text-tertiary hover:border-border-default hover:text-text-secondary transition-colors" onClick={openCommandPalette} whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}>
        <Search size={14} />
        <span className="flex-1 text-left">Search projects, commands...</span>
        <kbd className="hidden sm:inline-flex items-center rounded border border-border-default px-1.5 py-0.5 text-[10px] font-mono text-text-tertiary"><span className="text-xs">⌘</span>K</kbd>
      </motion.button>
      <div className="flex-1" />
      <motion.button className="flex items-center gap-1.5 h-8 rounded-lg bg-accent-purple hover:bg-accent-purple-soft px-3 text-xs font-medium text-white transition-colors" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={() => createProject("New Production")}><Plus size={14} />New Production</motion.button>
      <motion.div className={cn("flex items-center gap-1.5 h-7 rounded-full border px-3 text-[11px] font-mono", activeAgents > 0 ? "border-accent-purple/30 bg-accent-purple/10 text-accent-purple" : "border-border-subtle bg-surface-raised text-text-tertiary")} whileHover={{ scale: 1.02 }}>
        <motion.div className="w-1.5 h-1.5 rounded-full" animate={{ backgroundColor: activeAgents > 0 ? "#7C3AED" : "#5C5C78", scale: activeAgents > 0 ? [1, 1.3, 1] : 1 }} transition={activeAgents > 0 ? { duration: 1.5, repeat: Infinity } : {}} />
        {activeAgents > 0 ? `${activeAgents} agents` : "idle"}
      </motion.div>
      <div className="hidden md:flex items-center gap-2">
        <div className="flex items-center gap-1.5 h-7 rounded-full border border-border-subtle bg-surface-raised px-3 text-[11px] font-mono text-text-tertiary"><Circle size={6} className="fill-success text-success" />GPU ready</div>
        <div className="flex items-center gap-1.5 h-7 rounded-full border border-border-subtle bg-surface-raised px-3 text-[11px] font-mono text-text-tertiary">Queue: 0</div>
      </div>
      <motion.div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent-purple to-accent-blue flex items-center justify-center text-[10px] font-bold text-white cursor-pointer" whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}>DL</motion.div>
    </header>
  );
}
