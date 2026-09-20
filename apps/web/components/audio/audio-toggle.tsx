"use client";

import { Volume2, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAudioStore } from "@/stores/use-audio-store";

/**
 * Mute / unmute for the game audio. Autoplaying sound needs a visible way to silence it, so this is
 * shown on every page the ambience plays on (see AmbienceController). Master and music volumes
 * already exist in the audio store for a future settings screen; this is deliberately just the
 * one button.
 */
export function AudioToggle() {
  const muted = useAudioStore((state) => state.muted);
  const toggleMuted = useAudioStore((state) => state.toggleMuted);
  const label = muted ? "Unmute game audio" : "Mute game audio";

  return (
    <button
      type="button"
      onClick={toggleMuted}
      aria-pressed={muted}
      aria-label={label}
      title={label}
      className={cn(
        "flex h-9 w-9 items-center justify-center rounded-full border border-border-strong bg-void-elevated/80 backdrop-blur transition-colors hover:text-ink",
        muted ? "text-ink-faint" : "text-ink-muted"
      )}
    >
      {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
    </button>
  );
}
