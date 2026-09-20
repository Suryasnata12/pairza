"use client";

import { Clock } from "lucide-react";
import { cn, formatCountdown } from "@/lib/utils";
import { formatTimeLimit } from "@/lib/session-clock";
import type { SessionClock } from "@/lib/use-session-clock";
import type { SessionDetail } from "@/types";

const ENDED_TONE = "border-urgent-coral/30 bg-urgent-coral-dim text-urgent-coral";
const SOLVED_TONE = "border-signal-teal/30 bg-signal-teal-dim text-signal-teal";

/**
 * Purely presentational. It holds no duration and does no time math of its own:
 * `clock` (see useSessionClock) counts down to the server's `expires_at`, and
 * `session.status` decides what to say once things are over. The backend is the
 * only authority on when a session actually ends.
 */
export function CountdownTimer({ session, clock }: { session: SessionDetail; clock: SessionClock }) {
  let label: string;
  let tone: string;

  if (session.status === "SOLVED") {
    label = "Solved";
    tone = SOLVED_TONE;
  } else if (session.status === "EXPIRED") {
    label = "Time's up";
    tone = ENDED_TONE;
  } else if (session.status !== "ACTIVE") {
    label = "Ended";
    tone = ENDED_TONE;
  } else {
    label = formatCountdown(clock.secondsLeft);
    tone =
      clock.urgency === "critical"
        ? "border-urgent-coral/40 bg-urgent-coral-dim text-urgent-coral animate-pulse-urgent"
        : clock.urgency === "urgent"
          ? "border-urgent-coral/30 bg-urgent-coral-dim/60 text-urgent-coral"
          : "border-border-subtle bg-white/5 text-ink-muted";
  }

  return (
    <div
      role="timer"
      title={`Time limit: ${formatTimeLimit(session.duration_seconds)}`}
      className={cn("flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-sm", tone)}
    >
      <Clock className="h-3.5 w-3.5" />
      {label}
    </div>
  );
}
