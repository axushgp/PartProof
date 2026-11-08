import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#55D6C2] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0E12] disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-[#55D6C2] text-[#0B0E12] font-semibold hover:bg-[#42BCA9] shadow-sm active:translate-y-[0.5px]",
        secondary:
          "bg-[#151E27] text-[#F3F5F7] border border-white/10 hover:bg-[#1B2530] hover:border-white/20 active:translate-y-[0.5px]",
        outline:
          "border border-white/12 bg-transparent text-[#F3F5F7] hover:bg-white/[0.06] hover:border-white/20 active:translate-y-[0.5px]",
        destructive:
          "bg-rose-950/60 text-rose-200 border border-rose-700/60 hover:bg-rose-900/60 hover:border-rose-600 active:translate-y-[0.5px]",
        ghost:
          "text-zinc-300 hover:bg-white/[0.06] hover:text-white active:translate-y-[0.5px]",
        link: "text-[#55D6C2] underline-offset-4 hover:underline p-0 h-auto",
        success:
          "bg-emerald-950/60 text-emerald-200 border border-emerald-700/60 hover:bg-emerald-900/60 hover:border-emerald-600 active:translate-y-[0.5px]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-6 text-base",
        icon: "h-9 w-9",
        "icon-sm": "h-7 w-7",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  isLoading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, isLoading = false, children, disabled, ...props }, ref) => {
    if (asChild) {
      return (
        <Slot
          className={cn(buttonVariants({ variant, size, className }))}
          ref={ref}
          {...props}
        >
          {children}
        </Slot>
      );
    }

    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && <Loader2 className="h-4 w-4 animate-spin text-current" />}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
