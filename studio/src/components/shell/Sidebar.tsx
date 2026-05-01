"use client";

import { motion } from "framer-motion";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { Film, FolderOpen, Bot, Mic, Sliders, Settings, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const NAV_ITEMS = [
  { id: "studio", icon: Film, label: "Studio" },
  { id: "projects", icon: FolderOpen, label: "Projects" },
  { id: "agents", icon: Bot, label: "AI Agents" },
  { id: "narration", icon: Mic, label: "Narration" },
  { id: "timeline", icon: Sliders, label: "Timeline" },
  { id: "settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  const { sidebarExpanded, toggleSidebar } = useUiStore();
  const { currentProjectId, projects, setCurrentProject, createProject } = useProjectStore();

  return (
    <motion.aside
      className="relative flex flex-col h-full border-r border-border-subtle bg-surface-sunken/80"
      animate={{ width: sidebarExpanded ? 240 : 60 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
    >
      <div className={cn("flex items-center h-14 border-b border-border-subtle px-3", sidebarExpanded ? "gap-3" : "justify-center")}>
        <motion.div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-purple to-accent-blue flex items-center justify-center shrink-0" whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
          <Film size={16} className="text-white" />
        </motion.div>
        <motion.span className="text-sm font-semibold text-text-primary whitespace-nowrap overflow-hidden" animate={{ opacity: sidebarExpanded ? 1 : 0, width: sidebarExpanded ? "auto" : 0 }}>MoneyPrinter Studio</motion.span>
      </div>

      <motion.button
        className={cn("flex items-center mx-2 mt-3 rounded-lg bg-accent-purple/15 hover:bg-accent-purple/25 border border-accent-purple/30 transition-colors", sidebarExpanded ? "px-3 py-2 gap-2" : "justify-center py-2")}
        whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
        onClick={() => createProject("New Production")}
      >
        <Plus size={16} className="text-accent-purple shrink-0" />
        <motion.span className="text-xs font-medium text-accent-purple whitespace-nowrap overflow-hidden" animate={{ opacity: sidebarExpanded ? 1 : 0, width: sidebarExpanded ? "auto" : 0 }}>New Production</motion.span>
      </motion.button>

      <nav className="flex-1 mt-4 px-2 space-y-1">
        {NAV_ITEMS.map((item) => (
          <Tooltip key={item.id}>
            <TooltipTrigger asChild>
              <motion.button
                className={cn("flex items-center w-full rounded-lg transition-all group", sidebarExpanded ? "px-3 py-2 gap-3" : "justify-center py-2", item.id === "studio" ? "bg-accent-purple/10 text-accent-purple" : "text-text-tertiary hover:text-text-primary hover:bg-surface-overlay")}
                whileHover={{ x: 2 }} whileTap={{ scale: 0.98 }}
              >
                <item.icon size={18} className="shrink-0" />
                <motion.span className="text-sm whitespace-nowrap overflow-hidden" animate={{ opacity: sidebarExpanded ? 1 : 0, width: sidebarExpanded ? "auto" : 0 }}>{item.label}</motion.span>
                {item.id === "studio" && <motion.div className="absolute left-0 w-0.5 h-6 rounded-r-full bg-accent-purple shadow-glow-purple" layoutId="activeNav" transition={{ type: "spring", stiffness: 400, damping: 35 }} />}
              </motion.button>
            </TooltipTrigger>
            {!sidebarExpanded && <TooltipContent side="right">{item.label}</TooltipContent>}
          </Tooltip>
        ))}
      </nav>

      {sidebarExpanded && (
        <div className="px-3 pb-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary mb-2 px-1">Recent</div>
          <div className="space-y-0.5">
            {projects.slice(0, 3).map((p) => (
              <motion.button key={p.id} className={cn("flex items-center gap-2 w-full px-2 py-1.5 rounded-md text-xs transition-colors", p.id === currentProjectId ? "bg-accent-purple/10 text-accent-purple" : "text-text-secondary hover:bg-surface-overlay hover:text-text-primary")} whileHover={{ x: 2 }} onClick={() => setCurrentProject(p.id)}>
                <div className="w-5 h-5 rounded bg-accent-purple/20 flex items-center justify-center text-[9px] font-bold text-accent-purple">{p.name.slice(0, 2).toUpperCase()}</div>
                <span className="truncate">{p.movieTitle || p.name}</span>
              </motion.button>
            ))}
          </div>
        </div>
      )}

      <motion.button className="flex items-center justify-center h-10 border-t border-border-subtle text-text-tertiary hover:text-text-primary transition-colors" onClick={toggleSidebar} whileTap={{ scale: 0.95 }}>
        {sidebarExpanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </motion.button>
    </motion.aside>
  );
}
