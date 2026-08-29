import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold font-mono tracking-wide",
  {
    variants: {
      variant: {
        default: "bg-white/8 text-ink-muted",
        teal: "bg-signal-teal-dim text-signal-teal",
        violet: "bg-signal-violet-dim text-signal-violet",
        coral: "bg-urgent-coral-dim text-urgent-coral",
        gold: "bg-gold-dim text-gold",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
