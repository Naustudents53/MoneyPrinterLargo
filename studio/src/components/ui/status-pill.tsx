"use client";

import { cn } from "@/lib/utils";

export type PillStatus =
  | "uploaded"
  | "rendering"
  | "draft"
  | "failed"
  | "pending"
  | "uploading"
  | "queued"
  | "running"
  | "done"
  | "error"
  | "cancelled";

const MAP: Record<PillStatus, { label: string; color: string; bg: string }> = {
  uploaded:  { label: "Uploaded",  color: "#4ADE80", bg: "rgba(74,222,128,0.10)" },
  rendering: { label: "Rendering", color: "#F59E0B", bg: "rgba(245,158,11,0.10)" },
  draft:     { label: "Draft",     color: "#A8A29E", bg: "rgba(168,162,158,0.10)" },
  failed:    { label: "Failed",    color: "#F87171", bg: "rgba(248,113,113,0.10)" },
  pending:   { label: "Pending",   color: "#60A5FA", bg: "rgba(96,165,250,0.10)" },
  uploading: { label: "Uploading", color: "#E8A24F", bg: "rgba(232,162,79,0.12)" },
  queued:    { label: "Queued",    color: "#A8A29E", bg: "rgba(168,162,158,0.10)" },
  running:   { label: "Running",   color: "#E8A24F", bg: "rgba(232,162,79,0.12)" },
  done:      { label: "Done",      color: "#4ADE80", bg: "rgba(74,222,128,0.10)" },
  error:     { label: "Error",     color: "#F87171", bg: "rgba(248,113,113,0.10)" },
  cancelled: { label: "Cancelled", color: "#A8A29E", bg: "rgba(168,162,158,0.10)" },
};

export function StatusPill({
  status,
  size = "sm",
  label,
  className,
}: {
  status: PillStatus;
  size?: "xs" | "sm";
  label?: string;
  className?: string;
}) {
  const s = MAP[status] || MAP.draft;
  const padding = size === "xs" ? "px-[7px] py-[2px]" : "px-[9px] py-[3px]";
  const fontSize = size === "xs" ? "text-[10px]" : "text-[11px]";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-[5px] rounded-full font-medium tracking-[0.01em] border",
        padding,
        fontSize,
        className,
      )}
      style={{
        background: s.bg,
        color: s.color,
        borderColor: `${s.color}33`,
      }}
    >
      <span
        className="block h-[5px] w-[5px] rounded-full shrink-0"
        style={{ background: s.color }}
      />
      {label ?? s.label}
    </span>
  );
}
