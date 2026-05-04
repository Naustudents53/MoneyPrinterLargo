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
import { Film, Rocket } from "lucide-react";

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

  const { projects, currentProjectId, updateStep, completeStep, createProject } = projectStore;
  const { productions, currentProductionId, updateStep: updateProdStep, completeStep: completeProdStep, createProduction } = productionStore;

  const project = projects.find((p) => p.id === currentProjectId);
  const production = productions.find((p) => p.id === currentProductionId);
  const activeEntity = isShortLong ? production : project;

  const heading =
    type === "short"
      ? "MoneyPrinter Shorts"
      : type === "long"
      ? "MoneyPrinter Long"
      : "MoneyPrinter Studio";

  const subtitle =
    type === "short"
      ? "AI-powered YouTube Shorts production"
      : type === "long"
      ? "AI-powered long-form video production"
      : "AI-powered movie recap production";

  if (!activeEntity) {
    return (
      <motion.div
        className="flex-1 flex items-center justify-center relative"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        {/* Adopt ?job=<id> from the URL when the user lands here from the
            Task Monitor. Wrapped in Suspense because next/navigation's
            useSearchParams suspends during prerender. */}
        {isShortLong && type && (
          <Suspense fallback={null}>
            <JobAdopter type={type} />
          </Suspense>
        )}
        {/* Atmósfera de fondo */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full bg-accent-purple/5 blur-[150px]"
/>
          <div className="absolute bottom-1/4 right-1/3 w-[400px] h-[300px] rounded-full bg-accent-blue/4 blur-[120px]"
/>
        </div>

        <div className="text-center space-y-8 relative z-10">
          {/* Logo principal */}
          <motion.div
            className="relative w-28 h-28 rounded-3xl flex items-center justify-center mx-auto"
            style={{
              background: "linear-gradient(135deg, rgba(124,58,237,0.2), rgba(59,130,246,0.15))",
              border: "1px solid rgba(124,58,237,0.25)",
              boxShadow: "0 0 60px rgba(124,58,237,0.15), inset 0 1px 0 rgba(255,255,255,0.05)",
            }}
            animate={{
              rotate: [0, 2, -2, 0],
              scale: [1, 1.02, 1],
            }}
            transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
          >
            <Film size={48} className="text-accent-purple-soft" />
            {/* Anillo decorativo */}
            <div className="absolute inset-[-4px] rounded-3xl border border-accent-purple/10 animate-pulse-slow"
/>
          </motion.div>

          <div className="space-y-3">
            <h1 className="text-4xl font-bold text-text-primary tracking-tight">
              {heading}
              <span
                className="text-transparent bg-clip-text"
                style={{
                  backgroundImage: "linear-gradient(135deg, #A78BFA, #60A5FA)",
                }}
              >
                {" "}Studio
              </span>
            </h1>
            <p className="text-sm text-text-muted">
              {subtitle}
            </p>
          </div>

          <motion.button
            className="flex items-center gap-2.5 px-7 py-3.5 rounded-xl text-white text-sm font-semibold tracking-wide transition-all mx-auto"
            style={{
              background: "linear-gradient(135deg, #7C3AED, #5B21B6)",
              boxShadow:
                "0 0 30px rgba(124,58,237,0.3), inset 0 1px 0 rgba(255,255,255,0.1)",
              border: "1px solid rgba(124,58,237,0.4)",
            }}
            whileHover={{
              scale: 1.04,
              boxShadow:
                "0 0 45px rgba(124,58,237,0.4), inset 0 1px 0 rgba(255,255,255,0.15)",
            }}
            whileTap={{ scale: 0.97 }}
            onClick={() =>
              isShortLong && type
                ? createProduction(type, "New Production")
                : createProject("New Production")
            }
          >
            <Rocket size={16} />
            New Production
          </motion.button>
        </div>
      </motion.div>
    );
  }

  const activeStages = isShortLong ? SHORT_STAGES : STAGES;
  const currentStep = activeEntity.currentStep;
  const completedSteps = activeEntity.completedSteps;
  const StageComponent = activeStages[currentStep]?.component || activeStages[0].component;

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
          initial={{ opacity: 0, x: 60, filter: "blur(4px)" }}
          animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, x: -60, filter: "blur(4px)" }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        >
          <StageComponent
            onComplete={handleComplete}
          />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
