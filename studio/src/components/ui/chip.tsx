"use client";

import { cn } from "@/lib/utils";
import type { CSSProperties, ReactNode } from "react";

export function Chip({
  children,
  color,
  className,
  style,
  mono = true,
}: {
  children: ReactNode;
  color?: string;
  className?: string;
  style?: CSSProperties;
  mono?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-[2px] text-[11px] font-medium tracking-[0.01em]",
        mono && "font-mono",
        className,
      )}
      style={{
        background: color ? `${color}15` : "var(--color-surf-2)",
        border: `1px solid ${color ? `${color}30` : "var(--color-hairline)"}`,
        color: color ?? "var(--color-text-secondary)",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
