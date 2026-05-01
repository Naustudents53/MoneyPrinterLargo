"use client";

import { create } from "zustand";

export type ProductionType = "short" | "long" | "recap";

export interface ThumbnailConfig {
  text: string;
  font: string;
  overlayText?: string;
  colorTheme: "dark" | "cosmic" | "war" | "neon";
}

export interface ProductionConfig {
  type: ProductionType;
  topic: string;
  seriesId?: string;
  accountId?: string;
  voiceId: string;
  imageMode: "ai" | "photos";
  imageStyle: string;
  imagePrompts: string[];
  thumbnail: ThumbnailConfig;
  musicTrack?: string;
  narrativePrompt?: string;
  script?: string;
  narrationUrl?: string;
  videoPath?: string;
}

export interface Production {
  id: string;
  name: string;
  config: ProductionConfig;
  currentStep: number;
  completedSteps: number[];
  jobId?: string;
  jobStatus?: "queued" | "running" | "done" | "error" | "cancelled";
  jobProgress?: number;
}

interface ProductionState {
  productions: Production[];
  currentProductionId: string | null;
  createProduction: (type: ProductionType, name: string, config?: Partial<ProductionConfig>) => void;
  setCurrentProduction: (id: string) => void;
  updateConfig: (partial: Partial<ProductionConfig>) => void;
  updateStep: (step: number) => void;
  completeStep: (step: number) => void;
  setJobId: (jobId: string) => void;
  setJobStatus: (status: Production["jobStatus"]) => void;
  setJobProgress: (progress: number) => void;
  setScript: (script: string) => void;
  setImagePrompts: (prompts: string[]) => void;
  setNarrationUrl: (url: string) => void;
  setVideoPath: (path: string) => void;
}

const DEFAULT_THUMBNAIL: ThumbnailConfig = {
  text: "",
  font: "Inter",
  colorTheme: "cosmic",
};

export const useProductionStore = create<ProductionState>((set) => ({
  productions: [],
  currentProductionId: null,

  createProduction: (type, name, config = {}) =>
    set((state) => {
      const id = crypto.randomUUID();
      const production: Production = {
        id,
        name,
        config: {
          type,
          topic: config.topic || "",
          seriesId: config.seriesId,
          accountId: config.accountId,
          voiceId: config.voiceId || "",
          imageMode: config.imageMode || "ai",
          imageStyle: config.imageStyle || "",
          imagePrompts: config.imagePrompts || [],
          thumbnail: config.thumbnail || DEFAULT_THUMBNAIL,
          musicTrack: config.musicTrack,
          narrativePrompt: config.narrativePrompt,
          script: config.script,
          narrationUrl: config.narrationUrl,
          videoPath: config.videoPath,
        },
        currentStep: 0,
        completedSteps: [],
      };
      return { productions: [...state.productions, production], currentProductionId: id };
    }),

  setCurrentProduction: (id) => set({ currentProductionId: id }),

  updateConfig: (partial) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, config: { ...p.config, ...partial } } : p
      ),
    })),

  updateStep: (step) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, currentStep: step } : p
      ),
    })),

  completeStep: (step) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? { ...p, completedSteps: [...new Set([...p.completedSteps, step])] }
          : p
      ),
    })),

  setJobId: (jobId) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, jobId } : p
      ),
    })),

  setJobStatus: (status) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, jobStatus: status } : p
      ),
    })),

  setJobProgress: (progress) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, jobProgress: progress } : p
      ),
    })),

  setScript: (script) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, config: { ...p.config, script } } : p
      ),
    })),

  setImagePrompts: (prompts) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? { ...p, config: { ...p.config, imagePrompts: prompts } }
          : p
      ),
    })),

  setNarrationUrl: (url) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? { ...p, config: { ...p.config, narrationUrl: url } }
          : p
      ),
    })),

  setVideoPath: (path) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId ? { ...p, config: { ...p.config, videoPath: path } } : p
      ),
    })),
}));
