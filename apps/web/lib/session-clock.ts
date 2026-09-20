/**
 * Pure timer math for the investigation workspace's countdown.
 *
 * No React, no DOM, and — deliberately — no idea how long any mystery lasts.
 * Every number here arrives from the backend on the session payload:
 * `expires_at` (the fixed deadline), `server_time` (the server's clock when it
 * answered), `duration_seconds` and `expiring_warning_seconds`. The
 * difficulty -> duration rule lives in one place, apps/api/app/mysteries/
 * difficulty.py; the client only counts down to the deadline it is handed.
 *
 * Kept free of imports and of non-erasable TypeScript syntax so it can also be
 * run directly by Node's type stripping for the unit tests in tests/.
 */

export type Urgency = "normal" | "urgent" | "critical";

/**
 * Server clock minus device clock, in milliseconds. Add it to `Date.now()` to
 * estimate the server's "now". This is what makes two players with different
 * device clocks see the same countdown. Returns 0 if the timestamp is
 * unparseable (i.e. fall back to trusting the device clock).
 */
export function clockOffsetMs(serverTimeIso: string, clientNowMs: number): number {
  const serverMs = Date.parse(serverTimeIso);
  return Number.isFinite(serverMs) ? serverMs - clientNowMs : 0;
}

/** Milliseconds until the deadline as the server sees it; never negative. */
export function remainingMs(expiresAtIso: string, clientNowMs: number, offsetMs: number): number {
  const expiresMs = Date.parse(expiresAtIso);
  if (!Number.isFinite(expiresMs)) return 0;
  return Math.max(0, expiresMs - (clientNowMs + offsetMs));
}

/**
 * Whole seconds to display. Rounds UP so a fresh 5-minute session reads 5:00
 * (not 4:59) and only reaches 0:00 at the deadline itself.
 */
export function displaySeconds(remainingMillis: number): number {
  return Math.ceil(Math.max(0, remainingMillis) / 1000);
}

/**
 * Styling tier for the countdown. `warningSeconds` is the server-provided
 * threshold (the same one that triggers the `session.expiring` event);
 * "critical" is simply the final half of that window.
 */
export function urgencyFor(secondsLeft: number, warningSeconds: number): Urgency {
  if (secondsLeft <= warningSeconds / 2) return "critical";
  if (secondsLeft <= warningSeconds) return "urgent";
  return "normal";
}

/** "5 min", "30 min", "1 hr", "1 hr 30 min" — for showing a server-provided time limit. */
export function formatTimeLimit(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || !Number.isFinite(totalSeconds)) return "—";
  const minutes = Math.round(totalSeconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} hr` : `${hours} hr ${rest} min`;
}
