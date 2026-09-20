"use client";

import { useEffect, useState } from "react";
import { AudioToggle } from "@/components/audio/audio-toggle";
import { audioManager } from "@/lib/audio";

const AMBIENCE = "investigation_ambient_01" as const;

/**
 * Mounted ONCE in the root layout, so it survives every client-side navigation: the ambience starts
 * with the first page (the landing page at "/") and plays as one continuous track across the whole
 * app: no restart when moving between landing, login, home or an investigation. Only a full page
 * reload starts it again.
 *
 * Browsers won't play sound before the visitor has interacted with the page, so on a cold load
 * it begins at the first click, tap or key press (the manager waits for that, see audio-manager.ts).
 *
 * The mute button is drawn only after mount because the saved preference lives in localStorage:
 * rendering it during server render would show the default state and then mismatch on hydration.
 */
export function AmbienceController() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    audioManager.play(AMBIENCE);
    return () => audioManager.stop(AMBIENCE);
  }, []);

  if (!mounted) return null;
  return (
    <div className="fixed bottom-4 left-4 z-40">
      <AudioToggle />
    </div>
  );
}
