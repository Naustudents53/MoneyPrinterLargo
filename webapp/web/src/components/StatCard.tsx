import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "flat";
  accent?: "primary" | "accent" | "gold" | "success";
  className?: string;
}

const accentStyles: Record<NonNullable<StatCardProps["accent"]>, {
  rule: string;
  iconBg: string;
  iconColor: string;
  wash: string;
}> = {
  primary: {
    rule: "bg-primary",
    iconBg: "bg-primary/10",
    iconColor: "text-primary",
    wash: "from-primary/8 to-transparent",
  },
  accent: {
    rule: "bg-accent",
    iconBg: "bg-accent/10",
    iconColor: "text-accent",
    wash: "from-accent/8 to-transparent",
  },
  gold: {
    rule: "bg-gold",
    iconBg: "bg-gold/15",
    iconColor: "text-gold",
    wash: "from-gold/10 to-transparent",
  },
  success: {
    rule: "bg-success",
    iconBg: "bg-success/10",
    iconColor: "text-success",
    wash: "from-success/8 to-transparent",
  },
};

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  accent = "primary",
  className,
}: StatCardProps) {
  const a = accentStyles[accent];
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-lg p-5 studio-surface studio-hover",
        className
      )}
    >
      {/* studio top rule — semantic accent */}
      <span aria-hidden className={cn("absolute left-5 top-0 h-[3px] w-12 rounded-b-full", a.rule)} />
      {/* soft corner wash */}
      <div
        className={cn(
          "absolute -top-16 -right-16 h-40 w-40 rounded-full bg-gradient-to-br blur-2xl opacity-80 transition-opacity duration-300 group-hover:opacity-100",
          a.wash
        )}
      />
      <div className="relative flex items-start justify-between pt-3">
        <div className="space-y-1.5">
          <div className="eyebrow">{label}</div>
          <div className="font-display text-3xl font-bold tracking-tight tabular-nums">
            {value}
          </div>
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </div>
        {Icon && (
          <div className={cn("rounded-lg p-2.5 ring-1 ring-inset ring-foreground/5", a.iconBg, a.iconColor)}>
            <Icon className="h-5 w-5" strokeWidth={1.75} />
          </div>
        )}
      </div>
    </div>
  );
}
