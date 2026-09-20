"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clockOffsetMs, displaySeconds, remainingMs, urgencyFor, type Urgency } from "@/lib/session-clock";
import type { SessionDetail } from "@/types";

/** How often the display refreshes. Sub-second so the digits flip in step with the server's second boundaries. */
const TICK_MS = 250;
/** While the clock reads zero but the server still says ACTIVE, how often to ask it to settle the session. */
const SETTLE_RETRY_MS = 1500;

export interface SessionClock {
  /** Whole seconds left, rounded up; 0 once the deadline has passed. */
  secondsLeft: number;
  /** True once the (server-synchronised) clock has reached the deadline. */
  isTimeUp: boolean;
  urgency: Urgency;
}

/**
 * The one countdown for an investigation.
 *
 * It holds no duration of its own: it counts down to the server's `expires_at`,
 * corrected by `server_time` so a wrong device clock can't skew it. Both players
 * therefore see the same remaining time, and a page refresh — which just refetches
 * the same `expires_at` — can't reset it.
 *
 * Purely presentational: the backend alone decides when a session is over. When
 * the clock reaches zero on a session the server still reports as ACTIVE, this
 * asks the server to settle it (a fetch of the session runs the backend's expiry
 * check) and keeps asking until it does.
 */
export function useSessionClock(session: SessionDetail): SessionClock {
  const queryClient = useQueryClient();

  // Re-derived only when a fresh server_time arrives (i.e. on each refetch), not on every tick.
  const offsetMs = useMemo(() => clockOffsetMs(session.server_time, Date.now()), [session.server_time]);

  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, []);

  const remaining = remainingMs(session.expires_at, nowMs, offsetMs);
  const secondsLeft = displaySeconds(remaining);
  const isTimeUp = remaining <= 0;
  const awaitingServer = isTimeUp && session.status === "ACTIVE";

  useEffect(() => {
    if (!awaitingServer) return;
    const settle = () => queryClient.invalidateQueries({ queryKey: ["session"] });
    settle();
    const id = setInterval(settle, SETTLE_RETRY_MS);
    return () => clearInterval(id);
  }, [awaitingServer, queryClient]);

  return { secondsLeft, isTimeUp, urgency: urgencyFor(secondsLeft, session.expiring_warning_seconds) };
}
