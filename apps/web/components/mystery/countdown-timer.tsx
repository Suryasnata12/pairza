"use client";

import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { cn, formatCountdown } from "@/lib/utils";

/**
 * Purely cosmetic. The backend is the only authority on expiry — this
 * just counts down locally from `expiresAt` for a smooth UI, and a
 * WebSocket `session.expired` event (or the next poll) will correct
 * anything a client clock gets wrong. Nothing here is trusted for
 * actually ending the session.
 */
export function CountdownTimer({ expiresAt }: { expiresAt: string }) {
  const [secondsLeft, setSecondsLeft] = useState(() =>
    Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000))
  );

  useEffect(() => {
    const interval = setInterval(() => {
      setSecondsLeft(Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)));
    }, 1000);
    return () => clearInterval(interval);
  }, [expiresAt]);

  const isUrgent = secondsLeft < 3600; // under an hour
  const isCritical = secondsLeft < 300; // under 5 minutes

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-sm",
        isCritical
          ? "border-urgent-coral/40 bg-urgent-coral-dim text-urgent-coral animate-pulse-urgent"
          : isUrgent
            ? "border-urgent-coral/30 bg-urgent-coral-dim/60 text-urgent-coral"
            : "border-border-subtle bg-white/5 text-ink-muted"
      )}
    >
      <Clock className="h-3.5 w-3.5" />
      {secondsLeft > 0 ? formatCountdown(secondsLeft) : "Expired"}
    </div>
  );
}
