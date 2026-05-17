import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:translate-y-0 disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[inset_0_1px_0_hsl(var(--foreground)/.16),0_16px_34px_-26px_hsl(var(--primary)/.85)] hover:-translate-y-0.5 hover:bg-primary/90 active:translate-y-0 active:scale-[.98]",
        brand:
          "relative overflow-hidden bg-brand-gradient text-background shadow-[inset_0_1px_0_hsl(var(--foreground)/.18),0_16px_40px_-26px_hsl(var(--primary)/.85)] hover:-translate-y-0.5 hover:shadow-[inset_0_1px_0_hsl(var(--foreground)/.18),0_22px_52px_-30px_hsl(var(--accent)/.70)] active:translate-y-0 active:scale-[.98] font-semibold before:absolute before:inset-y-0 before:w-1/2 before:-translate-x-full before:bg-white/20 before:skew-x-[-18deg] hover:before:animate-[mpl-scan_900ms_cubic-bezier(.16,1,.3,1)]",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:-translate-y-0.5 hover:bg-destructive/90 active:scale-[.98]",
        outline:
          "border border-border/20 bg-background/50 shadow-sm backdrop-blur hover:-translate-y-0.5 hover:bg-surface/80 hover:border-primary/30 active:scale-[.98]",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:-translate-y-0.5 hover:bg-secondary/80 active:scale-[.98]",
        ghost: "hover:bg-surface/80 hover:text-foreground active:scale-[.98]",
        link: "text-primary underline-offset-4 hover:underline",
        soft: "bg-primary/10 text-primary hover:-translate-y-0.5 hover:bg-primary/20",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-6 text-base",
        xl: "h-12 rounded-lg px-8 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
