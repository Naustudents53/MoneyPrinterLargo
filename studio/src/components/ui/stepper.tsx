"use client";

import { cn } from "@/lib/utils";

export function Stepper({
  steps,
  current,
  completed = [],
  onChange,
  className,
}: {
  steps: string[];
  current: number;
  completed?: number[];
  onChange?: (index: number) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-0 px-6 h-[52px] border-b border-[var(--color-hairline)] shrink-0 overflow-x-auto",
        className,
      )}
    >
      {steps.map((step, i) => {
        const done = completed.includes(i) || i < current;
        const active = i === current;
        const reachable = done || active;
        return (
          <div key={step} className="flex items-center shrink-0">
            <button
              type="button"
              onClick={() => reachable && onChange?.(i)}
              className={cn(
                "flex items-center gap-2 px-[10px] py-[6px] rounded-md transition-all duration-150",
                active && "bg-[var(--color-amber-dim)] border border-[var(--color-amber-ring)]",
                !active && "border border-transparent",
                done && "text-[var(--color-text-primary)]",
                active && "text-[var(--color-amber)]",
                !done && !active && "text-[var(--color-text-tertiary)]",
                reachable ? "cursor-pointer" : "cursor-default",
              )}
            >
              <span
                className={cn(
                  "flex h-[22px] w-[22px] items-center justify-center rounded-full shrink-0 text-[11px] font-semibold border",
                )}
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
                {done ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "text-[12px] whitespace-nowrap",
                  active ? "font-semibold" : "font-normal",
                )}
              >
                {step}
              </span>
            </button>
            {i < steps.length - 1 && (
              <span className="block h-px w-5 bg-[var(--color-hairline)] shrink-0" />
            )}
          </div>
        );
      })}
    </div>
  );
}
