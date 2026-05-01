"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Download, Mic, Clapperboard, Users, Palette, Brain } from "lucide-react";

interface AnalysisNode { id: string; label: string; icon: React.ReactNode; status: "pending" | "running" | "complete"; }

const INITIAL_NODES: AnalysisNode[] = [
  { id: "download", label: "Downloading film", icon: <Download size={16} />, status: "pending" },
  { id: "transcribe", label: "Transcribing audio", icon: <Mic size={16} />, status: "pending" },
  { id: "scenes", label: "Detecting scenes", icon: <Clapperboard size={16} />, status: "pending" },
  { id: "characters", label: "Identifying characters", icon: <Users size={16} />, status: "pending" },
  { id: "themes", label: "Extracting themes", icon: <Palette size={16} />, status: "pending" },
  { id: "analyze", label: "AI story analysis", icon: <Brain size={16} />, status: "pending" },
];

export function StageAnalyze({ onComplete }: { onComplete?: () => void }) {
  const [nodes, setNodes] = useState<AnalysisNode[]>(INITIAL_NODES);
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    (async () => {
      const copy = [...INITIAL_NODES];
      for (let i = 0; i < copy.length; i++) {
        setNodes((prev) => prev.map((n, j) => (j === i ? { ...n, status: "running" as const } : n)));
        await new Promise((r) => setTimeout(r, 1400 + Math.random() * 1000));
        setNodes((prev) => prev.map((n, j) => (j === i ? { ...n, status: "complete" as const } : n)));
        setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ✓ ${copy[i].label} completed`]);
      }
      onComplete?.();
    })();
  }, []);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex items-center justify-center p-12">
        <div className="grid grid-cols-3 gap-x-12 gap-y-8">
          {nodes.map((node, i) => (
            <motion.div key={node.id} className="flex flex-col items-center gap-3" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}>
              <motion.div
                className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 relative ${node.status === "complete" ? "bg-success/10 border-success/30 text-success" : node.status === "running" ? "bg-accent-purple/10 border-accent-purple text-accent-purple" : "bg-surface-raised border-border-default text-text-tertiary"}`}
                animate={node.status === "running" ? { scale: [1, 1.08, 1], rotate: [0, 3, -2, 0] } : node.status === "complete" ? { scale: [1, 1.12, 1] } : {}}
                transition={node.status === "running" ? { duration: 2, repeat: Infinity } : { duration: 0.5 }}
              >
                {node.status === "complete" && <motion.div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-success flex items-center justify-center" initial={{ scale: 0 }} animate={{ scale: 1 }}><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg></motion.div>}
                {node.icon}
              </motion.div>
              <span className={`text-xs font-medium text-center ${node.status === "complete" ? "text-success" : node.status === "running" ? "text-accent-purple" : "text-text-tertiary"}`}>{node.label}</span>
              {node.status === "running" && (
                <div className="h-1 w-16 bg-surface-sunken rounded-full overflow-hidden"><motion.div className="h-full bg-accent-purple rounded-full" animate={{ width: ["0%", "100%"] }} transition={{ duration: 1.5, repeat: Infinity }} /></div>
              )}
            </motion.div>
          ))}
        </div>
      </div>
      <div className="w-80 border-l border-border-subtle bg-surface-sunken/60 p-4 overflow-y-auto">
        <div className="flex items-center gap-2 mb-4"><div className="w-2 h-2 rounded-full bg-success animate-pulse" /><span className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Live Log</span></div>
        <div className="space-y-1 font-mono text-[11px]">
          {logs.map((log, i) => <motion.div key={i} className="text-text-tertiary" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.04 }}>{log}</motion.div>)}
          {nodes.some((n) => n.status === "running") && <div className="text-accent-purple animate-pulse">&gt; Processing...</div>}
        </div>
      </div>
    </div>
  );
}
