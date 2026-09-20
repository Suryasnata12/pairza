import type { SoundDefinition } from "./audio-manager";

/**
 * Every sound Pairza can play. (The ambience is started app-wide by components/audio/ambience-controller.tsx.) Files live in apps/web/public/audio/ and are served from /audio/.
 *
 * To add a sound: drop the file into public/audio/, add one entry below, then call
 * `audioManager.play("<id>")` from wherever it belongs (import from "@/lib/audio").
 * Looping sounds (`loop: true`) keep exactly one instance until `stop()`; one-shot effects
 * (`loop: false`) can overlap themselves and clean up on their own.
 *
 * Planned, NOT yet added — each becomes a one-shot entry like the ones a future PR will write:
 *   answer_correct_01, answer_correct_02, answer_wrong_01, answer_wrong_02, clue_discovery,
 *   evidence_inspect, evidence_unlock, evidence_connection, mystery_solved
 * (Effects will also want their own "sfx" volume channel: see SOUND_CHANNELS in audio-manager.ts.)
 *
 * `sources` is a preference-ordered list, so an .m4a/.mp3 fallback can be added later for browsers
 * that can't decode Ogg (older Safari) without touching any calling code.
 */
export const SOUNDS = {
  investigation_ambient_01: {
    sources: [{ src: "/audio/investigation_ambient_01.ogg", type: "audio/ogg" }],
    channel: "music",
    loop: true,
    gain: 1,
    fadeInMs: 1500,
    fadeOutMs: 800,
  },
} satisfies Record<string, SoundDefinition>;

export type SoundId = keyof typeof SOUNDS;
