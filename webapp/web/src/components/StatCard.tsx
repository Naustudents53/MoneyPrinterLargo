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

const accentStyles = {
  primary: "from-primary/15 to-primary/0 text-primary",
  accent: "from-accent/15 to-accent/0 text-accent",
  gold: "from-gold/15 to-gold/0 text-gold",
  success: "from-success/15 to-success/0 text-success",
};

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  accent = "primary",
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-border/60 bg-card p-5 shadow-sm transition-all hover:border-border hover:shadow-md",
        className
      )}
    >
      <div
        className={cn(
          "absolute -top-12 -right-12 h-40 w-40 rounded-full bg-gradient-to-br blur-2xl opacity-60",
          accentStyles[accent]
        )}
      />
      <div className="relative flex items-start justify-between">
        <div className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </div>
          <div className="font-display text-3xl font-bold tracking-tight">{value}</div>
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </div>
        {Icon && (
          <div
            className={cn(
              "rounded-lg p-2.5 bg-gradient-to-br",
              accentStyles[accent]
            )}
          >
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
    </div>
  );
}
