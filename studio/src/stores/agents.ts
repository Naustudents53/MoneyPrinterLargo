"use client";

import { create } from "zustand";

export interface Agent {
  id: string;
  name: string;
  status: "idle" | "working" | "error" | "offline";
  task?: string;
  progress?: number;
}

interface AgentState {
  agents: Agent[];
  jobQueue: number;
  gpuStatus: "idle" | "busy" | "error";
  updateAgent: (id: string, update: Partial<Agent>) => void;
  setQueueSize: (size: number) => void;
  setGpuStatus: (status: "idle" | "busy" | "error") => void;
}

const DEFAULT_AGENTS: Agent[] = [
  { id: "scraper", name: "Film Scraper", status: "idle" },
  { id: "transcriber", name: "Transcriber", status: "idle" },
  { id: "scene-detector", name: "Scene Detector", status: "idle" },
  { id: "narrator", name: "Narrator", status: "idle" },
  { id: "editor", name: "Video Editor", status: "idle" },
];

export const useAgentStore = create<AgentState>((set) => ({
  agents: DEFAULT_AGENTS,
  jobQueue: 0,
  gpuStatus: "idle",
  updateAgent: (id, update) => set((state) => ({ agents: state.agents.map((a) => (a.id === id ? { ...a, ...update } : a)) })),
  setQueueSize: (size) => set({ jobQueue: size }),
  setGpuStatus: (status) => set({ gpuStatus: status }),
}));
