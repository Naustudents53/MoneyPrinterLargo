"use client";

/* eslint-disable react-hooks/set-state-in-effect */

import { AnimatePresence, motion } from "framer-motion";
import { Search, Zap } from "lucide-react";
import { useUiStore } from "@/stores/ui";
import { useProjectStore } from "@/stores/project";
import { useRef, useState, useEffect } from "react";

const SUGGESTIONS = [
  "New production: Metropolis (1927)",
  "Upload to YouTube",
  "Open last project",
  "Generate movie recap",
  "Settings: change voice",
];

export function CommandPalette() {
  const { commandPaletteOpen, closeCommandPalette } = useUiStore();
  const { createProject } = useProjectStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [instanceKey, setInstanceKey] = useState(0);

  const filtered = query
    ? SUGGESTIONS.filter((s) => s.toLowerCase().includes(query.toLowerCase()))
    : SUGGESTIONS;

  useEffect(() => {
    if (commandPaletteOpen) {
      setInstanceKey((k) => k + 1);
    }
  }, [commandPaletteOpen]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeCommandPalette();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (commandPaletteOpen) {
          closeCommandPalette();
        } else {
          useUiStore.getState().openCommandPalette();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [commandPaletteOpen, closeCommandPalette]);

  return (
    <AnimatePresence>
      {commandPaletteOpen && (
        <>
          {/** Backdrop */}
          <motion.div
            className="fixed inset-0 z-50 backdrop-blur-sm"
            style={{ background: "rgba(2,2,5,0.7)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeCommandPalette}
          />

          {/** Modal */}
          <motion.div
            className="fixed top-[20%] left-1/2 -translate-x-1/2 z-50 w-full max-w-lg"
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            transition={{ duration: 0.2 }}
          >
            <div
              className="overflow-hidden"
              style={{
                background: "linear-gradient(180deg, rgba(28,28,43,0.98), rgba(14,14,24,0.98))",
                border: "1px solid rgba(124,58,237,0.15)",
                borderRadius: "16px",
                boxShadow: "0 24px 64px rgba(0,0,0,0.5), 0 0 40px rgba(124,58,237,0.08)",
              }}
            >
              {/** Search input */}
              <div
                className="flex items-center gap-3 px-4 py-3 border-b"
                style={{ borderColor: "rgba(30,30,50,0.5)" }}
              >
                <Search size={16} className="text-text-muted shrink-0" />
                <input
                  key={instanceKey}
                  ref={inputRef}
                  defaultValue=""
                  autoFocus
                  className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
                  placeholder="Search projects, commands..."
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setSelected(0);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown")
                      setSelected((s) => Math.min(s + 1, filtered.length - 1));
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setSelected((s) => Math.max(s - 1, 0));
                    }
                    if (e.key === "Enter" && filtered[selected]) {
                      if (filtered[selected].toLowerCase().includes("metropolis"))
                        createProject("New Production", "Metropolis (1927)");
                      closeCommandPalette();
                    }
                  }}
                />
                <kbd className="text-[10px] font-mono text-text-muted">esc</kbd>
              </div>

              {/** Results */}
              <div className="max-h-60 overflow-y-auto p-2">
                {filtered.map((item, i) => (
                  <motion.button
                    key={item}
                    className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm text-left transition-all"
                    style={
                      i === selected
                        ? {
                            background: "rgba(124,58,237,0.08)",
                            color: "#A78BFA",
                          }
                        : {
                            color: "#9090B0",
                          }
                    }
                    whileHover={
                      i !== selected
                        ? { backgroundColor: "rgba(255,255,255,0.02)" }
                        : {}
                    }
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03 }}
                    onMouseEnter={() => setSelected(i)}
                    onClick={() => {
                      if (item.toLowerCase().includes("metropolis"))
                        createProject("New Production", "Metropolis (1927)");
                      closeCommandPalette();
                    }}
                  >
                    <Zap
                      size={14}
                      className="shrink-0"
                      style={{
                        color: i === selected ? "#A78BFA" : "#3A3A55",
                      }}
                    />
                    {item}
                  </motion.button>
                ))}
              </div>

              {/** Footer */}
              <div
                className="flex items-center gap-3 px-4 py-2.5 border-t text-[10px] text-text-muted"
                style={{ borderColor: "rgba(30,30,50,0.5)" }}
              >
                <span>
                  <kbd className="text-xs">↑↓</kbd> navigate
                </span>
                <span>
                  <kbd className="text-xs">↵</kbd> select
                </span>
                <span>
                  <kbd className="text-xs">esc</kbd> close
                </span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
