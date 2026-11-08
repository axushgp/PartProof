import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium border transition-colors select-none",
  {
    variants: {
      variant: {
        default:
          "border-white/10 bg-[#151E27] text-zinc-200",
        secondary:
          "border-white/8 bg-[#111820] text-zinc-300",
        destructive:
          "border-rose-800/60 bg-rose-950/50 text-rose-300",
        success:
          "border-emerald-800/60 bg-emerald-950/50 text-emerald-300",
        warning:
          "border-amber-700/60 bg-amber-950/50 text-amber-300",
        accent:
          "border-cyan-700/60 bg-cyan-950/50 text-cyan-200",
        outline:
          "border-white/15 text-zinc-300 bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  dotClass?: string;
}

function Badge({ className, variant, dotClass, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props}>
      {dotClass && <span className={cn("h-1.5 w-1.5 rounded-full", dotClass)} />}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
