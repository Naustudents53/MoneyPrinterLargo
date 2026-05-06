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
      aria-label="MoneyPrinter Pro"
    >
      <defs>
        <linearGradient id="mpp-g" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="hsl(var(--brand-start))" />
          <stop offset=".55" stopColor="hsl(var(--brand-mid))" />
          <stop offset="1" stopColor="hsl(var(--brand-end))" />
        </linearGradient>
        <linearGradient id="mpp-gold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fde68a" />
          <stop offset="1" stopColor="#f59e0b" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="14" fill="url(#mpp-g)" />
      <path
        d="M16 22h32v6H16zM18 30h28v18a4 4 0 0 1-4 4H22a4 4 0 0 1-4-4z"
        fill="hsl(var(--background))"
        opacity=".9"
      />
      <rect x="22" y="34" width="20" height="10" rx="2" fill="url(#mpp-gold)" />
      <circle cx="32" cy="39" r="2.6" fill="hsl(var(--background))" />
      <path
        d="M32 14v6M28 16l4 4 4-4"
        stroke="#fde68a"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

export function WordMark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <Logo size={32} />
      <div className="leading-tight">
        <div className="font-display font-bold text-[15px] tracking-tight">
          <span className="brand-text">MoneyPrinter</span>{" "}
          <span className="text-foreground">Pro</span>
        </div>
        <div className="text-[10px] text-muted-foreground tracking-widest uppercase">
          Content Engine
        </div>
      </div>
    </div>
  );
}
