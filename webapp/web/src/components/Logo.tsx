import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: number;
}

export function Logo({ className, size = 36 }: LogoProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={cn("shrink-0", className)}
      aria-label="MoneyPrinter Largo"
    >
      <defs>
        <linearGradient id="mpl-g" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="hsl(var(--brand-start))" />
          <stop offset=".5" stopColor="hsl(var(--brand-mid))" />
          <stop offset="1" stopColor="hsl(var(--brand-end))" />
        </linearGradient>
        <linearGradient id="mpl-bill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="hsl(var(--brand-start))" />
          <stop offset="1" stopColor="hsl(var(--brand-mid))" />
        </linearGradient>
        <linearGradient id="mpl-bill-2" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="hsl(var(--brand-mid))" />
          <stop offset="1" stopColor="hsl(var(--brand-end))" />
        </linearGradient>
      </defs>

      {/* Rounded tile background */}
      <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#mpl-g)" />

      {/* Inner card panel — printer body */}
      <rect
        x="11"
        y="22"
        width="42"
        height="22"
        rx="4"
        fill="hsl(var(--background))"
        opacity=".94"
      />
      {/* Top intake slot */}
      <rect x="14" y="20" width="36" height="3" rx="1.5" fill="hsl(var(--background))" opacity=".55" />
      {/* Output bill — long, ribboning out the bottom (the "Largo" cue) */}
      <path
        d="M14 44 H50 V52 a3 3 0 0 1 -3 3 H17 a3 3 0 0 1 -3 -3 Z"
        fill="url(#mpl-bill)"
      />
      <path
        d="M14 49 H50"
        stroke="hsl(var(--background))"
        strokeOpacity=".35"
        strokeWidth="1"
      />
      {/* Bill medallion */}
      <circle cx="32" cy="50" r="2.4" fill="hsl(var(--background))" opacity=".9" />
      <circle cx="32" cy="50" r="1" fill="url(#mpl-bill-2)" />

      {/* Down-arrow / coin spit on top — emphasizing motion */}
      <path
        d="M32 8 v8 M27 12 l5 5 5 -5"
        stroke="hsl(var(--background))"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        opacity=".95"
      />

      {/* Subtle status LED */}
      <circle cx="48" cy="28" r="1.6" fill="hsl(var(--brand-end))" />
    </svg>
  );
}

export function WordMark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <Logo size={34} />
      <div className="leading-tight">
        <div className="font-display font-bold text-[15px] tracking-tight">
          <span className="brand-text">MoneyPrinter</span>{" "}
          <span className="text-foreground">Largo</span>
        </div>
        <div className="text-[10px] text-muted-foreground tracking-[0.18em] uppercase">
          Long-form Studio
        </div>
      </div>
    </div>
  );
}
