import { create } from "zustand";
import {
  DEFAULT_AUDIO_SETTINGS,
  clampVolume,
  sanitizeAudioSettings,
  type AudioSettings,
} from "@/lib/audio/audio-manager";

/**
 * The player's audio preferences: master volume, music/ambience volume, mute.
 *
 * Persisted per DEVICE in localStorage (the same approach the reveal-seen flag already uses), not
 * on the server: the existing server-side preferences are matchmaking-only, and how loud you want
 * a laptop vs. a phone is a device choice anyway. Nothing else reads or writes this key.
 *
 * This store is only state + persistence. The audio engine follows it through the wiring in
 * "@/lib/audio" (index.ts), so UI components never touch the engine directly to change a volume.
 */
export const AUDIO_SETTINGS_STORAGE_KEY = "pairza_audio_settings_v1";

function loadSettings(): AudioSettings {
  if (typeof window === "undefined") return { ...DEFAULT_AUDIO_SETTINGS };
  try {
    return sanitizeAudioSettings(JSON.parse(window.localStorage.getItem(AUDIO_SETTINGS_STORAGE_KEY) ?? "null"));
  } catch {
    return { ...DEFAULT_AUDIO_SETTINGS }; // storage blocked or corrupt JSON: just use the defaults
  }
}

function saveSettings(settings: AudioSettings): void {
  try {
    window.localStorage.setItem(AUDIO_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // private mode / quota: the preference simply won't persist
  }
}

interface AudioState extends AudioSettings {
  setMasterVolume: (volume: number) => void;
  setMusicVolume: (volume: number) => void;
  setMuted: (muted: boolean) => void;
  toggleMuted: () => void;
}

export const useAudioStore = create<AudioState>((set) => ({
  ...loadSettings(),
  setMasterVolume: (volume) => set({ master: clampVolume(volume, DEFAULT_AUDIO_SETTINGS.master) }),
  setMusicVolume: (volume) => set({ music: clampVolume(volume, DEFAULT_AUDIO_SETTINGS.music) }),
  setMuted: (muted) => set({ muted }),
  toggleMuted: () => set((state) => ({ muted: !state.muted })),
}));

if (typeof window !== "undefined") {
  useAudioStore.subscribe((state) =>
    saveSettings({ master: state.master, music: state.music, muted: state.muted })
  );
}
