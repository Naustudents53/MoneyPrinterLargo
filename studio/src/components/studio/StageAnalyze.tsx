"use client";

import { motion } from "framer-motion";
import { Download, Mic, Clapperboard, Users, Palette, Brain } from "lucide-react";
import { useState, useEffect, useCallback } from "react";

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

  const runSequence = useCallback(async () => {
    const copy = [...INITIAL_NODES];
    for (let i = 0; i < copy.length; i++) {
      if (typeof window === "undefined") return;
      setNodes((prev) => prev.map((n, j) => (j === i ? { ...n, status: "running" as const } : n)));
      await new Promise((r) => setTimeout(r, 1400 + Math.random() * 1000));
      setNodes((prev) => prev.map((n, j) => (j === i ? { ...n, status: "complete" as const } : n)));
      setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ✓ ${copy[i].label} completed`]);
    }
    onComplete?.();
  }, [onComplete]);

  useEffect(() => {
    const timer = setTimeout(() => runSequence(), 0);
    return () => clearTimeout(timer);
  }, [runSequence]);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex items-center justify-center p-12">
        <div className="grid grid-cols-3 gap-x-16 gap-y-10">
          {nodes.map((node, i) => (
            <motion.div
              key={node.id}
              className="flex flex-col items-center gap-3"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
            >
              <motion.div
                className="w-20 h-20 rounded-2xl flex items-center justify-center border-2 relative"
                style={
                  node.status === "complete"
                    ? {
                        background: "rgba(16,185,129,0.06)",
                        borderColor: "rgba(16,185,129,0.2)",
                        color: "#10B981",
                      }
                    : node.status === "running"
                    ? {
                        background: "rgba(124,58,237,0.06)",
                        borderColor: "rgba(124,58,237,0.3)",
                        color: "#A78BFA",
                        boxShadow: "0 0 24px rgba(124,58,237,0.1)",
                      }
                    : {
                        background: "rgba(255,255,255,0.02)",
                        borderColor: "rgba(30,30,50,0.6)",
                        color: "#3A3A55",
                      }
                }
                animate={
                  node.status === "running"
                    ? { scale: [1, 1.06, 1], rotate: [0, 2, -1, 0] }
                    : node.status === "complete"
                    ? { scale: [1, 1.1, 1] }
                    : {}
                }
                transition={
                  node.status === "running"
                    ? { duration: 2, repeat: Infinity }
                    : { duration: 0.5 }
                }
              >
                {node.status === "complete" && (
                  <motion.div
                    className="absolute -top-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center"
                    style={{ background: "#10B981" }}
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                      <path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </motion.div>
                )}
                {node.icon}
              </motion.div>
              <span
                className="text-xs font-medium text-center"
                style={{
                  color:
                    node.status === "complete"
                      ? "#10B981"
                      : node.status === "running"
                      ? "#A78BFA"
                      : "#3A3A55",
                }}
              >
                {node.label}
              </span>
              {node.status === "running" && (
                <div className="h-1 w-16 rounded-full overflow-hidden"
                  style={{ background: "rgba(255,255,255,0.04)" }}
                >
                  <motion.div
                    className="h-full rounded-full"
                    style={{
                      background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
                      boxShadow: "0 0 8px rgba(124,58,237,0.3)",
                    }}
                    animate={{ width: ["0%", "100%"] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </div>

      <div
        className="w-80 flex flex-col"
        style={{
          borderLeft: "1px solid rgba(30,30,50,0.5)",
          background: "linear-gradient(180deg, rgba(6,6,16,0.6), rgba(8,8,15,0.4))",
        }}
      >
        <div className="flex items-center gap-2 px-4 py-3"
          style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}
        >
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: "#10B981" }}
          />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Live Log</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-[11px]">
          {logs.map((log, i) => (
            <motion.div
              key={i}
              style={{ color: "#5A5A7A" }}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.04 }}
            >
              {log}
            </motion.div>
          ))}
          {nodes.some((n) => n.status === "running") && (
            <div className="animate-pulse" style={{ color: "#A78BFA" }}>
              {"\u003e Processing..."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
