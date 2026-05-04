"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useProjectStore } from "@/stores/project";
import { useProductionStore } from "@/stores/production";
import { ProductionStepper } from "@/components/studio/ProductionStepper";
import { StageSelectMovie } from "@/components/studio/StageSelectMovie";
import { StageAnalyze } from "@/components/studio/StageAnalyze";
import { StageScript } from "@/components/studio/StageScript";
import { StageClips } from "@/components/studio/StageClips";
import { StageNarration } from "@/components/studio/StageNarration";
import { StageTimeline } from "@/components/studio/StageTimeline";
import { StageExport } from "@/components/studio/StageExport";
import { ConfigStage } from "@/components/studio/steps/ConfigStage";
import { ScriptStage } from "@/components/studio/steps/ScriptStage";
import { ImagesStage } from "@/components/studio/steps/ImagesStage";
import { ThumbnailStage } from "@/components/studio/steps/ThumbnailStage";
import { NarrationStage } from "@/components/studio/steps/NarrationStage";
import { RenderStage } from "@/components/studio/steps/RenderStage";
import { UploadStage } from "@/components/studio/steps/UploadStage";
import { JobAdopter } from "@/components/studio/JobAdopter";
import { Suspense } from "react";
import { Film, Plus } from "lucide-react";

const STAGES = [
  { key: "select", component: StageSelectMovie },
  { key: "analyze", component: StageAnalyze },
  { key: "script", component: StageScript },
  { key: "clips", component: StageClips },
  { key: "narration", component: StageNarration },
  { key: "timeline", component: StageTimeline },
  { key: "export", component: StageExport },
];

const SHORT_STAGES = [
  { key: "config", component: ConfigStage },
  { key: "script", component: ScriptStage },
  { key: "images", component: ImagesStage },
  { key: "thumbnail", component: ThumbnailStage },
  { key: "narration", component: NarrationStage },
  { key: "render", component: RenderStage },
  { key: "upload", component: UploadStage },
];

export function ProductionCanvas({ type }: { type?: "short" | "long" | "recap" }) {
  const isShortLong = type === "short" || type === "long";

  const projectStore = useProjectStore();
  const productionStore = useProductionStore();

  const {
    projects,
    currentProjectId,
    updateStep,
    completeStep,
    createProject,
  } = projectStore;
  const {
    productions,
    currentProductionId,
    updateStep: updateProdStep,
    completeStep: completeProdStep,
    createProduction,
  } = productionStore;

  const project = projects.find((p) => p.id === currentProjectId);
  const production = productions.find((p) => p.id === currentProductionId);
  const activeEntity = isShortLong ? production : project;

  const heading =
    type === "short"
      ? "New Short"
      : type === "long"
      ? "New Long-Form"
      : "Movie Recap";

  const subtitle =
    type === "short"
      ? "Vertical · ~45s · AI images + TTS · YouTube Shorts"
      : type === "long"
      ? "16:9 · 15–20 minutes · Series-aware long-form"
      : "Public-domain film → recap video";

  if (!activeEntity) {
    return (
      <div className="flex-1 flex items-center justify-center relative overflow-hidden">
        {isShortLong && type && (
          <Suspense fallback={null}>
            <JobAdopter type={type} />
          </Suspense>
        )}

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="text-center relative z-10 flex flex-col items-center gap-6 max-w-md px-6"
        >
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{
              background: "var(--color-surf-2)",
              border: "1px solid var(--color-hairline)",
            }}
          >
            <Film size={28} style={{ color: "var(--color-amber)" }} />
          </div>

          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-[-0.02em] text-[var(--color-text-primary)]">
              {heading}
            </h1>
            <p className="text-[13px] text-[var(--color-text-secondary)]">
              {subtitle}
            </p>
          </div>

          <button
            type="button"
            onClick={() =>
              isShortLong && type
                ? createProduction(type, "New Production")
                : createProject("New Production")
            }
            className="flex items-center gap-2 px-5 py-[9px] rounded-md text-[13px] font-semibold transition-opacity duration-150"
            style={{ background: "var(--color-amber)", color: "#0B0B0D" }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.88")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
          >
            <Plus size={14} strokeWidth={2.5} />
            Start production
          </button>
        </motion.div>
      </div>
    );
  }

  const activeStages = isShortLong ? SHORT_STAGES : STAGES;
  const currentStep = activeEntity.currentStep;
  const completedSteps = activeEntity.completedSteps;
  const StageComponent =
    activeStages[currentStep]?.component || activeStages[0].component;

  const handleComplete = () => {
    if (isShortLong) {
      completeProdStep(currentStep);
      if (currentStep < 6) updateProdStep(currentStep + 1);
    } else {
      completeStep(currentStep);
      if (currentStep < 6) updateStep(currentStep + 1);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 relative">
      {isShortLong && type && (
        <Suspense fallback={null}>
          <JobAdopter type={type} />
        </Suspense>
      )}
      <ProductionStepper
        currentStep={currentStep}
        completedSteps={completedSteps}
        onStepClick={isShortLong ? updateProdStep : updateStep}
        variant={isShortLong && type ? type : "default"}
      />
      <AnimatePresence mode="wait">
        <motion.div
          key={currentStep}
          className="flex-1 overflow-hidden"
          initial={{ opacity: 0, x: 32 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -32 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
        >
          <StageComponent onComplete={handleComplete} />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
