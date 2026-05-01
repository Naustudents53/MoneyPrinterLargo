"use client";

import { motion } from "framer-motion";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { Film, Settings, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const NAV_ITEMS = [
  { id: "studio", icon: Film, label: "Studio", href: "/" },
  { id: "shorts", icon: Film, label: "Shorts", href: "/shorts" },
  { id: "long", icon: Film, label: "Long", href: "/long" },
  { id: "settings", icon: Settings, label: "Settings", href: "/settings" },
];

export function Sidebar() {
  const { sidebarExpanded, toggleSidebar } = useUiStore();
  const { currentProjectId, projects, setCurrentProject, createProject } = useProjectStore();

  return (
    <motion.aside
      className="relative flex flex-col h-full z-10"
      style={{
        background: "linear-gradient(180deg, rgba(6,6,16,0.95) 0%, rgba(6,6,16,0.7) 100%)",
        borderRight: "1px solid rgba(30,30,50,0.5)",
      }}
      animate={{ width: sidebarExpanded ? 230 : 56 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
    >
      {/* Logo area */}
      <div
        className={cn(
          "flex items-center h-14 border-b border-border-ghost",
          sidebarExpanded ? "gap-3 px-3" : "justify-center px-2"
        )}
      >
        <motion.div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{
            background: "linear-gradient(135deg, #7C3AED, #3B82F6)",
            boxShadow: "0 0 16px rgba(124,58,237,0.25)",
          }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Film size={16} className="text-white" />
        </motion.div>
        <motion.span
          className="text-[13px] font-semibold text-text-primary whitespace-nowrap overflow-hidden tracking-tight"
          animate={{ opacity: sidebarExpanded ? 1 : 0, width: sidebarExpanded ? "auto" : 0 }}
        >
          MoneyPrinter
        </motion.span>
      </div>

      {/* New Production button */}
      <motion.button
        className={cn(
          "flex items-center mx-2 mt-3 rounded-lg transition-all",
          sidebarExpanded ? "px-3 py-2 gap-2" : "justify-center py-2"
        )}
        style={{
          background: "linear-gradient(135deg, rgba(124,58,237,0.12), rgba(59,130,246,0.08))",
          border: "1px solid rgba(124,58,237,0.2)",
        }}
        whileHover={{
          background: "linear-gradient(135deg, rgba(124,58,237,0.2), rgba(59,130,246,0.12))",
          borderColor: "rgba(124,58,237,0.35)",
          boxShadow: "0 0 20px rgba(124,58,237,0.1)",
        }}
        whileTap={{ scale: 0.98 }}
        onClick={() => createProject("New Production")}
      >
        <Plus size={16} className="text-accent-purple-soft shrink-0" />
        <motion.span
          className="text-xs font-medium text-accent-purple-soft whitespace-nowrap overflow-hidden"
          animate={{ opacity: sidebarExpanded ? 1 : 0, width: sidebarExpanded ? "auto" : 0 }}
        >
          New Production
        </motion.span>
      </motion.button>

      {/* Navigation */}
      <nav className="flex-1 mt-4 px-2 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <Tooltip key={item.id}>
            <TooltipTrigger asChild>
              <Link
                href={item.href}
                className={cn(
                  "flex items-center w-full rounded-lg transition-all group relative",
                  sidebarExpanded ? "px-3 py-2 gap-3" : "justify-center py-2",
                  item.id === "studio"
                    ? "text-accent-purple-soft"
                    : "text-text-tertiary hover:text-text-secondary"
                )}
                style={
                  item.id === "studio"
                    ? {
                        background: "linear-gradient(90deg, rgba(124,58,237,0.08), transparent)",
                      }
                    : {}
                }
              >
                <item.icon size={18} className="shrink-0" />
                <motion.span
                  className="text-[13px] whitespace-nowrap overflow-hidden"
                  animate={{ opacity: sidebarExpanded ? 1 : 0, width: sidebarExpanded ? "auto" : 0 }}
                >
                  {item.label}
                </motion.span>
                {item.id === "studio" && (
                  <motion.div
                    className="absolute left-0 w-[2px] h-5 rounded-r-full"
                    style={{
                      background: "linear-gradient(180deg, #7C3AED, #3B82F6)",
                      boxShadow: "0 0 8px rgba(124,58,237,0.5)",
                    }}
                    layoutId="activeNav"
                    transition={{ type: "spring", stiffness: 400, damping: 35 }}
                  />
                )}
              </Link>
            </TooltipTrigger>
            {!sidebarExpanded && <TooltipContent side="right">{item.label}</TooltipContent>}
          </Tooltip>
        ))}
      </nav>

      {/* Proyectos recientes */}
      {sidebarExpanded && (
        <div className="px-3 pb-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2 px-1">
            Recent
          </div>
          <div className="space-y-0.5">
            {projects.slice(0, 3).map((p) => (
              <motion.button
                key={p.id}
                className={cn(
                  "flex items-center gap-2 w-full px-2 py-1.5 rounded-md text-xs transition-colors",
                  p.id === currentProjectId
                    ? "text-accent-purple-soft"
                    : "text-text-secondary hover:bg-surface-raised hover:text-text-primary"
                )}
                style={
                  p.id === currentProjectId
                    ? { background: "rgba(124,58,237,0.06)" }
                    : {}
                }
                whileHover={{ x: 2 }}
                onClick={() => setCurrentProject(p.id)}
              >
                <div
                  className="w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold"
                  style={{
                    background: p.id === currentProjectId
                      ? "rgba(124,58,237,0.15)"
                      : "rgba(255,255,255,0.04)",
                    color: p.id === currentProjectId ? "#A78BFA" : "#5A5A7A",
                  }}
                >
                  {p.name.slice(0, 2).toUpperCase()}
                </div>
                <span className="truncate">{p.movieTitle || p.name}</span>
              </motion.button>
            ))}
          </div>
        </div>
      )}

      {/* Toggle */}
      <motion.button
        className="flex items-center justify-center h-10 border-t border-border-ghost text-text-muted hover:text-text-secondary transition-colors"
        onClick={toggleSidebar}
        whileTap={{ scale: 0.95 }}
      >
        {sidebarExpanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </motion.button>
    </motion.aside>
  );
}
