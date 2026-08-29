import * as React from "react";
import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          "flex min-h-[100px] w-full rounded-xl border border-border-subtle bg-void-elevated-2 px-4 py-3 text-sm text-ink placeholder:text-ink-faint transition-colors resize-none",
          "focus-visible:outline-none focus-visible:border-signal-teal/60 focus-visible:ring-1 focus-visible:ring-signal-teal/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...props}
      />
    );
  }
);
Textarea.displayName = "Textarea";

export { Textarea };
