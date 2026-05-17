import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: number;
}

/**
 * Brand badge — gradient square with mono "$" glyph. Mirrors the design
 * language across sidebar header, login screens, etc.
 */
export function Logo({ className, size = 32 }: LogoProps) {
  return (
    <div
      className={cn(
        "shrink-0 inline-flex items-center justify-center rounded-lg bg-brand-gradient-deep relative",
        className,
      )}
      style={{
        width: size,
        height: size,
        boxShadow: "inset 0 4px 14px -6px rgba(0,0,0,0.4)",
      }}
      aria-label="MoneyPrinter Largo"
    >
      <span
        className="font-mono font-bold leading-none"
        style={{
          color: "hsl(213 27% 6%)",
          fontSize: Math.round(size * 0.34),
          letterSpacing: "0",
        }}
      >
        $
      </span>
    </div>
  );
}

/**
 * Sidebar wordmark — brand badge + two-line label (MoneyPrinter / LARGO · v1.0.0).
 */
export function WordMark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5 min-w-0", className)}>
      <Logo size={32} />
      <div className="flex flex-col leading-tight min-w-0">
        <span className="font-display font-semibold text-[13px] text-foreground truncate">
          MoneyPrinter
        </span>
        <span className="font-mono text-[10px] text-muted-foreground truncate">
          LARGO · v1.0.0
        </span>
      </div>
    </div>
  );
}
