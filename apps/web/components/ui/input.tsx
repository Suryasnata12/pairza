import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          "flex h-11 w-full rounded-xl border border-border-subtle bg-void-elevated-2 px-4 py-2 text-sm text-ink placeholder:text-ink-faint transition-colors",
          "focus-visible:outline-none focus-visible:border-signal-teal/60 focus-visible:ring-1 focus-visible:ring-signal-teal/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
