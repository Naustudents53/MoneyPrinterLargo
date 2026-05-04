"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step {
  id: string;
  label: string;
}

const DEFAULT_STEPS: Step[] = [
  { id: "select",    label: "Select" },
  { id: "analyze",   label: "Analyze" },
  { id: "script",    label: "Script" },
  { id: "clips",     label: "Clips" },
  { id: "narration", label: "Voice" },
  { id: "timeline",  label: "Timeline" },
  { id: "export",    label: "Export" },
];

const SHORT_LONG_STEPS: Step[] = [
  { id: "config",    label: "Config" },
  { id: "script",    label: "Script" },
  { id: "images",    label: "Images" },
  { id: "thumbnail", label: "Thumbnail" },
  { id: "narration", label: "Voice" },
  { id: "render",    label: "Render" },
  { id: "upload",    label: "Upload" },
];

interface Props {
  currentStep: number;
  completedSteps: number[];
  onStepClick: (step: number) => void;
  variant?: "default" | "short" | "long";
}

export function ProductionStepper({
  currentStep,
  completedSteps,
  onStepClick,
  variant = "default",
}: Props) {
  const steps = variant === "default" ? DEFAULT_STEPS : SHORT_LONG_STEPS;
  return (
    <nav
      className="flex items-center gap-0 px-6 h-[52px] shrink-0 overflow-x-auto"
      style={{ borderBottom: "1px solid var(--color-hairline)" }}
    >
      {steps.map((step, i) => {
        const done = completedSteps.includes(i);
        const active = i === currentStep;
        const reachable = done || active;
        return (
          <div key={step.id} className="flex items-center shrink-0">
            <button
              type="button"
              onClick={() => reachable && onStepClick(i)}
              className={cn(
                "flex items-center gap-2 px-[10px] py-[6px] rounded-md transition-all duration-150",
                reachable ? "cursor-pointer" : "cursor-default",
              )}
              style={{
                background: active ? "var(--color-amber-dim)" : "transparent",
                border: active
                  ? "1px solid var(--color-amber-ring)"
                  : "1px solid transparent",
                color: active
                  ? "var(--color-amber)"
                  : done
                  ? "var(--color-text-primary)"
                  : "var(--color-text-tertiary)",
              }}
            >
              <span
                className="flex h-[22px] w-[22px] items-center justify-center rounded-full shrink-0 text-[11px] font-semibold border"
                style={{
                  background: active
                    ? "var(--color-amber)"
                    : done
                    ? "var(--color-success-bg)"
                    : "var(--color-surf-2)",
                  borderColor: active
                    ? "var(--color-amber)"
                    : done
                    ? "rgba(74,222,128,0.27)"
                    : "var(--color-hairline)",
                  color: active
                    ? "#0B0B0D"
                    : done
                    ? "var(--color-success)"
                    : "var(--color-text-tertiary)",
                }}
              >
                {done ? <Check size={12} /> : i + 1}
              </span>
              <span
                className="text-[12px] whitespace-nowrap"
                style={{ fontWeight: active ? 600 : 400 }}
              >
                {step.label}
              </span>
            </button>
            {i < steps.length - 1 && (
              <span className="block h-px w-5 bg-[var(--color-hairline)] shrink-0" />
            )}
          </div>
        );
      })}
    </nav>
  );
}
