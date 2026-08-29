import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold transition-all duration-200 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-teal/50 focus-visible:ring-offset-2 focus-visible:ring-offset-void",
  {
    variants: {
      variant: {
        primary:
          "bg-signal-teal text-void hover:bg-signal-teal/90 shadow-[0_0_24px_-4px_rgba(69,232,200,0.5)] hover:shadow-[0_0_32px_-2px_rgba(69,232,200,0.65)] active:scale-[0.98]",
        secondary:
          "bg-signal-violet text-white hover:bg-signal-violet/90 shadow-[0_0_24px_-4px_rgba(155,123,255,0.5)] active:scale-[0.98]",
        outline:
          "border border-border-strong bg-transparent text-ink hover:bg-white/5 active:scale-[0.98]",
        ghost: "bg-transparent text-ink-muted hover:text-ink hover:bg-white/5",
        destructive: "bg-urgent-coral text-white hover:bg-urgent-coral/90 active:scale-[0.98]",
        link: "text-signal-teal underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-5 py-2",
        sm: "h-9 px-4 text-[13px]",
        lg: "h-14 px-8 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
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
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
