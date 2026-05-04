"use client";

import { cn } from "@/lib/utils";
import { StatusPill, type PillStatus } from "@/components/ui/status-pill";
import { PlatformGlyph } from "@/components/ui/platform-glyph";

export interface VideoTileData {
  id: string;
  title: string;
  duration?: string;
  status: PillStatus;
  platform?: "youtube" | "twitter" | string;
  aspect: "9:16" | "16:9";
  thumb?: string;
  views?: string | null;
}

const SIZES = {
  sm: { vert: { w: 70, h: 124 }, horiz: { w: 160, h: 90 } },
  md: { vert: { w: 90, h: 160 }, horiz: { w: 200, h: 112 } },
  lg: { vert: { w: 110, h: 196 }, horiz: { w: 240, h: 135 } },
};

export function VideoTile({
  data,
  size = "md",
  onClick,
  className,
}: {
  data: VideoTileData;
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
  className?: string;
}) {
  const isVert = data.aspect === "9:16";
  const dims = SIZES[size][isVert ? "vert" : "horiz"];
  const thumb = data.thumb ?? (isVert ? "#1A2A3D" : "#1A1A1F");
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "shrink-0 flex flex-col gap-[6px] text-left",
        onClick && "cursor-pointer",
        className,
      )}
    >
      <div
        className="relative overflow-hidden rounded-lg border border-[var(--color-hairline)] flex items-center justify-center"
        style={{
          width: dims.w,
          height: dims.h,
          background: `linear-gradient(135deg, ${thumb}, ${thumb}88)`,
        }}
      >
        <span
          className="stripes pointer-events-none absolute inset-0 opacity-[0.15]"
          aria-hidden
        />
        <div className="absolute bottom-[6px] left-[6px] right-[6px] flex items-end justify-between">
          <StatusPill status={data.status} size="xs" />
          {data.platform && <PlatformGlyph platform={data.platform} size={16} />}
        </div>
        <span className="font-mono text-[9px] text-white/30 text-center px-1">
          {data.aspect}
        </span>
      </div>
      {size !== "sm" && (
        <div style={{ width: dims.w }}>
          <div className="text-[11px] font-medium text-[var(--color-text-primary)] leading-[1.4] truncate">
            {data.title}
          </div>
          <div className="font-mono text-[10px] text-[var(--color-text-tertiary)] mt-[2px] flex gap-[6px]">
            {data.duration && <span>{data.duration}</span>}
            {data.views && (
              <span className="text-[var(--color-success)]">{data.views}</span>
            )}
          </div>
        </div>
      )}
    </button>
  );
}
