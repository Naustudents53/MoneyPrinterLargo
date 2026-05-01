"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step { id: string; label: string; icon: string; }

const DEFAULT_STEPS: Step[] = [
  { id: "select", label: "Select", icon: "🎬" },
  { id: "analyze", label: "Analyze", icon: "🧠" },
  { id: "script", label: "Script", icon: "📝" },
  { id: "clips", label: "Clips", icon: "✂️" },
  { id: "narration", label: "Voice", icon: "🎙️" },
  { id: "timeline", label: "Timeline", icon: "🎞️" },
  { id: "export", label: "Export", icon: "📤" },
];

const SHORT_LONG_STEPS: Step[] = [
  { id: "config", label: "Config", icon: "⚙️" },
  { id: "script", label: "Script", icon: "📝" },
  { id: "images", label: "Images", icon: "🖼️" },
  { id: "thumbnail", label: "Thumbnail", icon: "🎨" },
  { id: "narration", label: "Voice", icon: "🎙️" },
  { id: "render", label: "Render", icon: "🎬" },
  { id: "upload", label: "Upload", icon: "📤" },
];

interface ProductionStepperProps {
  currentStep: number;
  completedSteps: number[];
  onStepClick: (step: number) => void;
  variant?: "default" | "short" | "long";
}

export function ProductionStepper({ currentStep, completedSteps, onStepClick, variant = "default" }: ProductionStepperProps) {
  const STEPS = variant === "default" ? DEFAULT_STEPS : SHORT_LONG_STEPS;

  return (
    <nav className="flex items-center gap-1 px-6 py-4 overflow-x-auto relative">
      {/* Línea de progreso sutil */}
      <div className="absolute bottom-5 left-6 right-6 h-[1px] bg-border-ghost"
/>
      <motion.div
        className="absolute bottom-5 left-6 h-[1px]"
        style={{
          background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
          boxShadow: "0 0 8px rgba(124,58,237,0.3)",
        }}
        initial={false}
        animate={{
          width: `${(currentStep / (STEPS.length - 1)) * 100}%`,
        }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      />

      {STEPS.map((step, index) => {
        const isCompleted = completedSteps.includes(index);
        const isCurrent = currentStep === index;

        return (
          <motion.button
            key={step.id}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm shrink-0 transition-all relative z-10",
              isCurrent && "",
              isCompleted && "",
              !isCompleted && !isCurrent && "text-text-muted"
            )}
            style={
              isCurrent
                ? {
                    background: "rgba(124,58,237,0.06)",
                    border: "1px solid rgba(124,58,237,0.15)",
                    color: "#A78BFA",
                  }
                : isCompleted
                ? {
                    background: "rgba(16,185,129,0.04)",
                    border: "1px solid rgba(16,185,129,0.1)",
                  }
                : {
                    background: "transparent",
                    border: "1px solid transparent",
                  }
            }
            onClick={() => onStepClick(index)}
            whileHover={
              !isCurrent
                ? {
                    backgroundColor: "rgba(255,255,255,0.02)",
                  }
                : {}
            }
            whileTap={{ scale: 0.97 }}
          >
            <motion.span
              className={cn(
                "flex items-center justify-center w-7 h-7 rounded-full text-xs shrink-0 relative",
                isCompleted
                  ? "bg-success/15 text-success"
                  : isCurrent
                  ? "bg-accent-purple text-white"
                  : "bg-surface-raised text-text-muted border border-border-ghost"
              )}
              style={
                isCurrent
                  ? {
                      boxShadow: "0 0 12px rgba(124,58,237,0.4)",
                    }
                  : {}
              }
              animate={
                isCurrent
                  ? {
                      scale: [1, 1.08, 1],
                      boxShadow: [
                        "0 0 0px rgba(124,58,237,0)",
                        "0 0 16px rgba(124,58,237,0.4)",
                        "0 0 0px rgba(124,58,237,0)",
                      ],
                    }
                  : { scale: 1 }
              }
              transition={isCurrent ? { duration: 2, repeat: Infinity } : {}}
            >
              {isCompleted ? <Check size={12} /> : step.icon}
            </motion.span>
            <span className="hidden md:inline whitespace-nowrap text-[13px]">
              {step.label}
            </span>
          </motion.button>
        );
      })}
    </nav>
  );
}
