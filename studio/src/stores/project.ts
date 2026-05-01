"use client";

import { create } from "zustand";

export interface MovieClip {
  id: string;
  startTime: number;
  endTime: number;
  thumbnail?: string;
  confidence: number;
  reason: string;
}

export interface Scene {
  id: string;
  title: string;
  timestamp: string;
  description: string;
  importance: number;
}

export interface TimelineTrack {
  id: string;
  type: "video" | "voice" | "music" | "effects";
  clips: TimelineClip[];
}

export interface TimelineClip {
  id: string;
  startTime: number;
  duration: number;
  sourceRef: string;
  trimmedStart?: number;
  trimmedEnd?: number;
}

export interface Project {
  id: string;
  name: string;
  movieTitle?: string;
  movieUrl?: string;
  posterUrl?: string;
  currentStep: number;
  completedSteps: number[];
  scenes: Scene[];
  clips: MovieClip[];
  script: string;
  narrationUrl?: string;
  timeline: TimelineTrack[];
  exportSettings: {
    resolution: "1080p" | "720p" | "480p";
    format: "mp4" | "mov";
    platform: "youtube-shorts" | "tiktok" | "youtube" | "custom";
  };
}

interface ProjectState {
  projects: Project[];
  currentProjectId: string | null;
  createProject: (name: string, movieTitle?: string, movieUrl?: string, posterUrl?: string) => void;
  setCurrentProject: (id: string) => void;
  updateStep: (step: number) => void;
  completeStep: (step: number) => void;
  setScenes: (scenes: Scene[]) => void;
  setClips: (clips: MovieClip[]) => void;
  setScript: (script: string) => void;
  setNarrationUrl: (url: string) => void;
  updateTimeline: (tracks: TimelineTrack[]) => void;
  updateExportSettings: (settings: Partial<Project["exportSettings"]>) => void;
}

const DEFAULT_TIMELINE: TimelineTrack[] = [
  { id: "video", type: "video", clips: [] },
  { id: "voice", type: "voice", clips: [] },
  { id: "music", type: "music", clips: [] },
  { id: "effects", type: "effects", clips: [] },
];

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  currentProjectId: null,
  createProject: (name, movieTitle, movieUrl, posterUrl) =>
    set((state) => {
      const id = crypto.randomUUID();
      const project: Project = {
        id, name, movieTitle, movieUrl, posterUrl,
        currentStep: 0, completedSteps: [],
        scenes: [], clips: [], script: "",
        timeline: DEFAULT_TIMELINE,
        exportSettings: { resolution: "1080p", format: "mp4", platform: "youtube" },
      };
      return { projects: [...state.projects, project], currentProjectId: id };
    }),
  setCurrentProject: (id) => set({ currentProjectId: id }),
  updateStep: (step) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, currentStep: step } : p) })),
  completeStep: (step) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, completedSteps: [...new Set([...p.completedSteps, step])] } : p) })),
  setScenes: (scenes) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, scenes } : p) })),
  setClips: (clips) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, clips } : p) })),
  setScript: (script) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, script } : p) })),
  setNarrationUrl: (url) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, narrationUrl: url } : p) })),
  updateTimeline: (tracks) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, timeline: tracks } : p) })),
  updateExportSettings: (settings) => set((state) => ({ projects: state.projects.map((p) => p.id === state.currentProjectId ? { ...p, exportSettings: { ...p.exportSettings, ...settings } } : p) })),
}));
