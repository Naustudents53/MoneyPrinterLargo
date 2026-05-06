"use client";

import { create } from "zustand";
import type { Stage } from "@/lib/api";

export type ProductionType = "short" | "long" | "recap";

export interface ThumbnailConfig {
  text: string;
  font: string;
  overlayText?: string;
  colorTheme: "dark" | "cosmic" | "war" | "neon";
}

export interface MetadataConfig {
  title: string;
  description: string;
  tags: string[];
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
  metadata?: MetadataConfig;
  presetId?: string;
  targetDuration?: 60 | 120 | 180;
}

export interface StageStatus {
  status: "idle" | "running" | "done" | "error";
  message?: string;
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
  stages?: Record<Stage, StageStatus>;
}

interface ProductionState {
  productions: Production[];
  currentProductionId: string | null;
  createProduction: (
    type: ProductionType,
    name: string,
    config?: Partial<ProductionConfig>
  ) => void;
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
  appendScriptChunk: (chunk: string) => void;
  setMetadata: (meta: MetadataConfig) => void;
  setStageStatus: (
    stage: Stage,
    status: StageStatus["status"],
    message?: string
  ) => void;
  clearArtifacts: () => void;
  // Adopt a backend job into the local store. Used by the deep-link
  // wizard (`/shorts?job=<id>`) when the user opens an in-progress task
  // from the Task Monitor — we hydrate the local Production with the
  // job's existing artifacts/state and reuse its job_id so SSE works.
  adoptJob: (
    type: ProductionType,
    jobId: string,
    seed: Partial<ProductionConfig>,
    initialStep?: number
  ) => void;
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
          metadata: config.metadata,
          presetId: config.presetId,
          targetDuration: config.targetDuration || 60,
        },
        currentStep: 0,
        completedSteps: [],
        stages: {} as Record<Stage, StageStatus>,
      };
      return {
        productions: [...state.productions, production],
        currentProductionId: id,
      };
    }),

  setCurrentProduction: (id) => set({ currentProductionId: id }),

  updateConfig: (partial) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? { ...p, config: { ...p.config, ...partial } }
          : p
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
        p.id === state.currentProductionId
          ? { ...p, config: { ...p.config, script } }
          : p
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
        p.id === state.currentProductionId
          ? { ...p, config: { ...p.config, videoPath: path } }
          : p
      ),
    })),

  appendScriptChunk: (chunk) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? {
              ...p,
              config: { ...p.config, script: (p.config.script || "") + chunk },
            }
          : p
      ),
    })),

  setMetadata: (meta) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? { ...p, config: { ...p.config, metadata: meta } }
          : p
      ),
    })),

  setStageStatus: (stage, status, message) =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? {
              ...p,
              stages: {
                ...(p.stages || {}),
                [stage]: { status, message },
              } as Record<Stage, StageStatus>,
            }
          : p
      ),
    })),

  clearArtifacts: () =>
    set((state) => ({
      productions: state.productions.map((p) =>
        p.id === state.currentProductionId
          ? {
              ...p,
              config: {
                ...p.config,
                script: undefined,
                imagePrompts: [],
                narrationUrl: undefined,
                videoPath: undefined,
                metadata: undefined,
              },
              stages: {} as Record<Stage, StageStatus>,
              jobProgress: undefined,
            }
          : p
      ),
    })),

  adoptJob: (type, jobId, seed, initialStep) =>
    set((state) => {
      // If we already adopted this job, just bring it back to current.
      const existing = state.productions.find((p) => p.jobId === jobId);
      if (existing) {
        return {
          ...state,
          currentProductionId: existing.id,
          productions: state.productions.map((p) =>
            p.id === existing.id
              ? {
                  ...p,
                  // Refresh seed fields with the latest server values.
                  config: { ...p.config, ...seed },
                  currentStep: initialStep ?? p.currentStep,
                }
              : p
          ),
        };
      }
      const id = crypto.randomUUID();
      const production: Production = {
        id,
        name: seed.topic || `Job ${jobId.slice(0, 8)}`,
        config: {
          type,
          topic: seed.topic || "",
          seriesId: seed.seriesId,
          accountId: seed.accountId,
          voiceId: seed.voiceId || "",
          imageMode: seed.imageMode || "ai",
          imageStyle: seed.imageStyle || "",
          imagePrompts: seed.imagePrompts || [],
          thumbnail: seed.thumbnail || DEFAULT_THUMBNAIL,
          musicTrack: seed.musicTrack,
          narrativePrompt: seed.narrativePrompt,
          script: seed.script,
          narrationUrl: seed.narrationUrl,
          videoPath: seed.videoPath,
          metadata: seed.metadata,
          presetId: seed.presetId,
        },
        currentStep: initialStep ?? 1,
        completedSteps: [],
        jobId,
        stages: {} as Record<Stage, StageStatus>,
      };
      return {
        productions: [...state.productions, production],
        currentProductionId: id,
      };
    }),
}));
