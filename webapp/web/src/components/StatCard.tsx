import { type LucideIcon, ArrowUp, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

type AccentName = "primary" | "accent" | "gold" | "success" | "lima" | "violeta";

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  /** Array of numeric samples — renders an inline sparkline if provided. */
  series?: number[];
  /** Visible delta label, e.g. "+33%". */
  delta?: string;
  deltaDir?: "up" | "down";
  accent?: AccentName;
  className?: string;
}

const ACCENT_VAR: Record<AccentName, string> = {
  primary: "var(--primary)",
  accent: "var(--accent)",
  gold: "var(--gold)",
  success: "var(--success)",
  lima: "var(--lima)",
  violeta: "var(--violeta)",
};

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  series,
  delta,
  deltaDir,
  accent = "primary",
  className,
}: StatCardProps) {
  const accentVar = ACCENT_VAR[accent];
  const deltaPositive = deltaDir === "up";
  const deltaColor = deltaPositive ? "hsl(var(--success))" : "hsl(var(--destructive))";

  return (
    <div
      className={cn(
        "group relative overflow-hidden studio-surface studio-hover px-[18px] pt-[18px] pb-4 min-h-[132px]",
        className,
      )}
    >
      {/* Top accent stripe */}
      <span
        aria-hidden
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{
          background: `linear-gradient(90deg, hsl(${accentVar}), transparent 72%)`,
          opacity: 0.9,
        }}
      />
      {/* Soft corner glow */}
      <div
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-16 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity"
        style={{
          background: `linear-gradient(0deg, hsl(${accentVar} / .10), transparent)`,
        }}
      />

      <div className="relative flex items-start justify-between mb-2">
        <span
          className="font-mono uppercase font-semibold text-[10px]"
          style={{ color: `hsl(${accentVar})` }}
        >
          {label}
        </span>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />}
      </div>

      <div className="relative flex items-baseline gap-2">
        <span className="font-mono font-semibold text-[32px] leading-none tabular-nums text-foreground">
          {value}
        </span>
        {delta && (
          <span
            className="inline-flex items-center gap-0.5 font-mono text-[11.5px] font-medium"
            style={{ color: deltaColor }}
          >
            {deltaPositive ? (
              <ArrowUp className="h-3 w-3" strokeWidth={2} />
            ) : (
              <ArrowDown className="h-3 w-3" strokeWidth={2} />
            )}
            {delta}
          </span>
        )}
      </div>

      <div className="relative flex items-end justify-between mt-1.5 min-h-[26px]">
        {hint && (
          <span className="font-mono text-[11px] text-muted-foreground">{hint}</span>
        )}
        {series && series.length > 1 && (
          <Sparkline data={series} colorVar={accentVar} w={84} h={26} />
        )}
      </div>
    </div>
  );
}

/** Inline SVG sparkline with subtle area fill + last-point dot. */
export function Sparkline({
  data,
  colorVar,
  w = 80,
  h = 24,
  strokeW = 1.4,
}: {
  data: number[];
  colorVar: string;
  w?: number;
  h?: number;
  strokeW?: number;
}) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => [i * step, h - ((v - min) / range) * (h - 3) - 1.5] as const);
  const d = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ");
  const fillD = `${d} L${w},${h} L0,${h} Z`;
  const last = pts[pts.length - 1];

  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      <path d={fillD} fill={`hsl(${colorVar})`} opacity="0.12" />
      <path
        d={d}
        fill="none"
        stroke={`hsl(${colorVar})`}
        strokeWidth={strokeW}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last[0]} cy={last[1]} r={2.2} fill={`hsl(${colorVar})`} />
    </svg>
  );
}
