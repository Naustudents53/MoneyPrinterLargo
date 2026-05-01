"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Search } from "lucide-react";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { useEffect, useRef, useState } from "react";

const SUGGESTIONS = ["New production: Metropolis (1927)", "Upload to YouTube", "Open last project", "Generate movie recap", "Settings: change voice"];

export function CommandPalette() {
  const { commandPaletteOpen, closeCommandPalette } = useUiStore();
  const { createProject } = useProjectStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);

  const filtered = query ? SUGGESTIONS.filter((s) => s.toLowerCase().includes(query.toLowerCase())) : SUGGESTIONS;

  useEffect(() => { if (commandPaletteOpen) { setTimeout(() => inputRef.current?.focus(), 50); setQuery(""); setSelected(0); } }, [commandPaletteOpen]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeCommandPalette();
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); commandPaletteOpen ? closeCommandPalette() : useUiStore.getState().openCommandPalette(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [commandPaletteOpen, closeCommandPalette]);

  return (
    <AnimatePresence>
      {commandPaletteOpen && (
        <>
          <motion.div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={closeCommandPalette} />
          <motion.div className="fixed top-[20%] left-1/2 -translate-x-1/2 z-50 w-full max-w-lg" initial={{ opacity: 0, y: -20, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -20, scale: 0.95 }} transition={{ duration: 0.2 }}>
            <div className="rounded-2xl border border-border-default bg-surface-overlay shadow-2xl overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
                <Search size={16} className="text-text-tertiary shrink-0" />
                <input ref={inputRef} className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary outline-none" placeholder="Search projects, commands..." value={query} onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
                  onKeyDown={(e) => { if (e.key === "ArrowDown") setSelected((s) => Math.min(s + 1, filtered.length - 1)); if (e.key === "ArrowUp") { e.preventDefault(); setSelected((s) => Math.max(s - 1, 0)); } if (e.key === "Enter" && filtered[selected]) { if (filtered[selected].toLowerCase().includes("metropolis")) createProject("New Production", "Metropolis (1927)"); closeCommandPalette(); } }} />
                <kbd className="text-[10px] font-mono text-text-tertiary">esc</kbd>
              </div>
              <div className="max-h-60 overflow-y-auto p-2">
                {filtered.map((item, i) => (
                  <motion.button key={item} className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm text-left transition-colors ${i === selected ? "bg-accent-purple/15 text-accent-purple" : "text-text-secondary hover:bg-surface-raised"}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
                    onMouseEnter={() => setSelected(i)}
                    onClick={() => { if (item.toLowerCase().includes("metropolis")) createProject("New Production", "Metropolis (1927)"); closeCommandPalette(); }}
                  >
                    <Search size={14} className="text-text-tertiary shrink-0" />{item}
                  </motion.button>
                ))}
              </div>
              <div className="flex items-center gap-3 px-4 py-2.5 border-t border-border-subtle text-[10px] text-text-tertiary"><span><kbd className="text-xs">↑↓</kbd> navigate</span><span><kbd className="text-xs">↵</kbd> select</span><span><kbd className="text-xs">esc</kbd> close</span></div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
