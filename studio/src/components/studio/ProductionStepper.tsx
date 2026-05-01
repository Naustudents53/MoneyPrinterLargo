"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step { id: string; label: string; icon: string; }

const STEPS: Step[] = [
  { id: "select-movie", label: "Select Movie", icon: "🎬" },
  { id: "analyze", label: "AI Analysis", icon: "🧠" },
  { id: "script", label: "Script", icon: "📝" },
  { id: "clips", label: "Clips", icon: "✂️" },
  { id: "narration", label: "Voice", icon: "🎙️" },
  { id: "timeline", label: "Timeline", icon: "🎞️" },
  { id: "export", label: "Export", icon: "📤" },
];

interface ProductionStepperProps { currentStep: number; completedSteps: number[]; onStepClick: (step: number) => void; }

export function ProductionStepper({ currentStep, completedSteps, onStepClick }: ProductionStepperProps) {
  return (
    <nav className="flex items-center gap-1 px-6 py-4 overflow-x-auto">
      {STEPS.map((step, index) => {
        const isCompleted = completedSteps.includes(index);
        const isCurrent = currentStep === index;
        return (
          <motion.button
            key={step.id}
            className={cn("flex items-center gap-2 px-3 py-2 rounded-xl text-sm shrink-0 transition-colors",
              isCurrent && "bg-accent-purple/15 text-accent-purple border border-accent-purple/30",
              isCompleted && "text-success hover:bg-surface-overlay border border-transparent",
              !isCompleted && !isCurrent && "text-text-secondary hover:bg-surface-overlay border border-transparent")}
            onClick={() => onStepClick(index)}
            whileTap={{ scale: 0.97 }}
          >
            <motion.span
              className={cn("flex items-center justify-center w-7 h-7 rounded-full text-xs shrink-0",
                isCompleted && "bg-success/20 text-success",
                isCurrent && "bg-accent-purple text-white",
                !isCompleted && !isCurrent && "bg-surface-raised text-text-secondary")}
              animate={isCurrent ? { scale: [1, 1.08, 1], boxShadow: ["0 0 0 rgba(124,58,237,0)", "0 0 12px rgba(124,58,237,0.4)", "0 0 0 rgba(124,58,237,0)"] } : { scale: 1 }}
              transition={isCurrent ? { duration: 2, repeat: Infinity } : {}}
            >
              {isCompleted ? <Check size={12} /> : step.icon}
            </motion.span>
            <span className="hidden md:inline whitespace-nowrap">{step.label}</span>
          </motion.button>
        );
      })}
    </nav>
  );
}
