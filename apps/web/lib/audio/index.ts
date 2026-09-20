import { useAudioStore } from "@/stores/use-audio-store";
import { AudioManager, type AudioSettings } from "./audio-manager";
import { SOUNDS } from "./sounds";

export { SOUNDS };
export type { SoundId } from "./sounds";

/**
 * THE audio manager: the only one in the app. Import it from here, never construct another.
 *
 *   import { audioManager } from "@/lib/audio";
 *   audioManager.play("investigation_ambient_01");
 */
export const audioManager = new AudioManager(SOUNDS);

// Keep the engine in step with the player's saved preferences, from the moment this module loads.
const pickSettings = (state: AudioSettings): AudioSettings => ({
  master: state.master,
  music: state.music,
  muted: state.muted,
});
audioManager.setSettings(pickSettings(useAudioStore.getState()));
useAudioStore.subscribe((state) => audioManager.setSettings(pickSettings(state)));
