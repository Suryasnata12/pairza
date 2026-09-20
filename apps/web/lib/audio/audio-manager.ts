/**
 * Pairza's game-audio engine.
 *
 * One AudioManager owns every sound the game plays. It knows nothing about
 * React, routes, or which sounds exist: the catalog is handed to it (see
 * ./sounds.ts) and screens ask it to `play(id)` / `stop(id)`.
 *
 * Why Web Audio rather than <audio loop>:
 *   - sample-accurate GAPLESS looping (an <audio> element leaves a small gap),
 *   - smooth fades and volume changes without timers,
 *   - volume control that also works on iOS, where element.volume is ignored,
 *   - decode-once buffers that later sound effects can overlap freely.
 *
 * Signal path:   source -> per-sound gain (level + fades)
 *                       -> channel gain   (the "music" volume)
 *                       -> master gain    (master volume / mute) -> speakers
 *
 * Adding a sound later = one entry in ./sounds.ts, then `audioManager.play(id)`
 * from wherever it belongs. Adding a volume channel (e.g. "sfx") = add it to
 * SOUND_CHANNELS, AudioSettings and DEFAULT_AUDIO_SETTINGS; the compiler points
 * at everything else.
 *
 * Deliberately free of imports and of non-erasable TypeScript syntax, so it can
 * be unit-tested by Node's type stripping with a fake AudioContext (tests/).
 * Every failure is swallowed into a single console warning: audio is decoration
 * and must never break the game.
 */

// ---------------------------------------------------------------------------
// Types & settings (pure)
// ---------------------------------------------------------------------------

/** Volume channels. The user-facing "music / ambience" volume is the "music" channel. */
export const SOUND_CHANNELS = ["music"] as const;
export type SoundChannel = (typeof SOUND_CHANNELS)[number];

export interface SoundSource {
  src: string;
  /** MIME type, used to skip formats the browser can't decode (e.g. "audio/ogg"). */
  type: string;
}

export interface SoundDefinition {
  /** Candidate files in order of preference; the first the browser can play is used. */
  sources: readonly SoundSource[];
  channel: SoundChannel;
  /** true = one instance that repeats until stopped; false = a one-shot effect that may overlap itself. */
  loop: boolean;
  /** Per-sound level (0-1) relative to its channel, to balance assets without re-exporting them. */
  gain: number;
  fadeInMs?: number;
  fadeOutMs?: number;
}

export type AudioSettings = Record<SoundChannel, number> & {
  master: number;
  muted: boolean;
};

/** Ambience is meant to sit quietly under the game, so the default is low. */
export const DEFAULT_AUDIO_SETTINGS: Readonly<AudioSettings> = {
  master: 1,
  music: 0.3,
  muted: false,
};

export function clampVolume(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : fallback;
}

/** Turns anything (e.g. parsed localStorage) into valid settings: bad or missing fields fall back to defaults. */
export function sanitizeAudioSettings(raw: unknown): AudioSettings {
  const source = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  return {
    master: clampVolume(source.master, DEFAULT_AUDIO_SETTINGS.master),
    music: clampVolume(source.music, DEFAULT_AUDIO_SETTINGS.music),
    muted: typeof source.muted === "boolean" ? source.muted : DEFAULT_AUDIO_SETTINGS.muted,
  };
}

// ---------------------------------------------------------------------------
// Browser environment (injectable so the logic is testable without a browser)
// ---------------------------------------------------------------------------

export interface AudioEnv {
  /** A new AudioContext, or null when Web Audio isn't available (server render, very old browsers). */
  createContext(): AudioContext | null;
  canPlayType(mimeType: string): boolean;
  fetchAudio(url: string): Promise<ArrayBuffer>;
  /** Calls `handler` on user gestures; returns a function that stops listening. */
  onUserGesture(handler: () => void): () => void;
  warn(message: string, error?: unknown): void;
}

// Events browsers accept as a "user activation" for unlocking audio (Safari wants click/touchend).
const GESTURE_EVENTS = ["pointerdown", "pointerup", "touchend", "click", "keydown"] as const;

function createBrowserEnv(): AudioEnv {
  return {
    createContext() {
      if (typeof window === "undefined" || typeof window.AudioContext === "undefined") return null;
      return new window.AudioContext();
    },
    canPlayType(mimeType) {
      return document.createElement("audio").canPlayType(mimeType) !== "";
    },
    async fetchAudio(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
      return response.arrayBuffer();
    },
    onUserGesture(handler) {
      for (const name of GESTURE_EVENTS) window.addEventListener(name, handler, { capture: true, passive: true });
      return () => {
        for (const name of GESTURE_EVENTS) window.removeEventListener(name, handler, true);
      };
    },
    warn(message, error) {
      console.warn(message, error);
    },
  };
}

// ---------------------------------------------------------------------------
// The manager
// ---------------------------------------------------------------------------

/** Time constant for volume/mute changes: settles in ~90 ms, fast enough to feel instant, slow enough not to click. */
const SETTINGS_SMOOTHING_S = 0.03;
/** setTargetAtTime reaches ~95% after three time constants, so a fade of N ms uses N/3. */
const timeConstantFor = (fadeMs: number) => Math.max(fadeMs, 1) / 1000 / 3;

interface LoopInstance {
  source: AudioBufferSourceNode;
  gain: GainNode;
  /** True during the fade-out; a play() in that window revives this instance instead of starting a second one. */
  stopping: boolean;
  timer: ReturnType<typeof setTimeout> | null;
}

export class AudioManager<Id extends string> {
  private readonly catalog: Readonly<Record<Id, SoundDefinition>>;
  private readonly env: AudioEnv;

  private ctx: AudioContext | null = null;
  private contextUnavailable = false;
  private masterGain: GainNode | null = null;
  private readonly channelGains = new Map<SoundChannel, GainNode>();
  private settings: AudioSettings = { ...DEFAULT_AUDIO_SETTINGS };

  /** Decoded audio, cached per sound (including a cached failure, so a missing file is fetched and reported once). */
  private readonly buffers = new Map<Id, Promise<AudioBuffer | null>>();
  /** The at-most-one running instance of each looping sound. */
  private readonly loops = new Map<Id, LoopInstance>();
  /** Loops the app currently wants playing — survives the async load and a not-yet-unlocked browser. */
  private readonly wanted = new Set<Id>();
  private readonly starting = new Set<Id>();
  private removeGestureListener: (() => void) | null = null;

  constructor(catalog: Readonly<Record<Id, SoundDefinition>>, env: AudioEnv = createBrowserEnv()) {
    this.catalog = catalog;
    this.env = env;
  }

  /** Starts a sound. Looping sounds are idempotent: calling again while playing changes nothing. */
  play(id: Id): void {
    const definition = this.catalog[id];
    if (!definition) return;

    if (!definition.loop) {
      void this.playOneShot(id, definition);
      return;
    }

    this.wanted.add(id);
    const existing = this.loops.get(id);
    if (existing) {
      if (existing.stopping) this.revive(existing, definition);
      return;
    }
    if (this.starting.has(id)) return;
    void this.startLoop(id, definition);
  }

  /** Stops a looping sound with its fade-out (or `fadeMs` if given). Safe to call when it isn't playing. */
  stop(id: Id, options?: { fadeMs?: number }): void {
    this.wanted.delete(id);
    const instance = this.loops.get(id);
    const definition = this.catalog[id];
    if (!instance || instance.stopping || !definition) return;

    const fadeMs = options?.fadeMs ?? definition.fadeOutMs ?? 0;
    const ctx = this.ctx;
    if (fadeMs <= 0 || !ctx) {
      this.teardown(id, instance);
      return;
    }
    instance.stopping = true;
    const now = ctx.currentTime;
    instance.gain.gain.cancelScheduledValues(now);
    instance.gain.gain.setTargetAtTime(0, now, timeConstantFor(fadeMs));
    instance.timer = setTimeout(() => this.teardown(id, instance), fadeMs + 50);
  }

  stopAll(): void {
    for (const id of new Set<Id>([...this.loops.keys(), ...this.wanted])) this.stop(id);
  }

  isPlaying(id: Id): boolean {
    const instance = this.loops.get(id);
    return instance !== undefined && !instance.stopping;
  }

  /** Applies volume/mute. Safe to call before any sound has played; the values are applied when audio starts. */
  setSettings(settings: AudioSettings): void {
    this.settings = sanitizeAudioSettings(settings);
    this.applySettings(false);
  }

  /** Explicitly resume a browser-suspended context; call from a click handler if a screen wants to be sure. */
  unlock(): void {
    const ctx = this.ctx;
    if (ctx && ctx.state !== "running") void ctx.resume().catch(() => {});
  }

  // --- internals -----------------------------------------------------------

  private async startLoop(id: Id, definition: SoundDefinition): Promise<void> {
    this.starting.add(id);
    try {
      const buffer = await this.loadBuffer(id, definition);
      const ctx = this.ctx;
      if (!buffer || !ctx) {
        this.wanted.delete(id); // unloadable: give up quietly until the next page load
        return;
      }
      // stop() may have been called (or another start finished) while the file was loading.
      if (!this.wanted.has(id) || this.loops.has(id)) return;
      const { source, gain } = this.spawn(ctx, buffer, definition);
      this.loops.set(id, { source, gain, stopping: false, timer: null });
    } finally {
      this.starting.delete(id);
    }
  }

  private async playOneShot(id: Id, definition: SoundDefinition): Promise<void> {
    const buffer = await this.loadBuffer(id, definition);
    const ctx = this.ctx;
    if (!buffer || !ctx) return;
    // Effects belong to a moment. If the browser hasn't been unlocked yet, drop it rather than
    // queueing it to blast out later when the context finally resumes.
    if (ctx.state !== "running") return;
    const { source, gain } = this.spawn(ctx, buffer, definition);
    source.onended = () => {
      source.disconnect();
      gain.disconnect();
    };
  }

  private spawn(ctx: AudioContext, buffer: AudioBuffer, definition: SoundDefinition) {
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = definition.loop;
    const gain = ctx.createGain();
    source.connect(gain);
    gain.connect(this.channelGains.get(definition.channel) as GainNode);

    const now = ctx.currentTime;
    if (definition.fadeInMs && definition.fadeInMs > 0) {
      gain.gain.setValueAtTime(0, now);
      gain.gain.setTargetAtTime(definition.gain, now, timeConstantFor(definition.fadeInMs));
    } else {
      gain.gain.setValueAtTime(definition.gain, now);
    }
    // If the context is still suspended (autoplay policy) this simply waits: it begins, fade included,
    // the moment the browser lets the context run.
    source.start(0);
    return { source, gain };
  }

  private revive(instance: LoopInstance, definition: SoundDefinition): void {
    const ctx = this.ctx;
    if (instance.timer) clearTimeout(instance.timer);
    instance.timer = null;
    instance.stopping = false;
    if (!ctx) return;
    const now = ctx.currentTime;
    instance.gain.gain.cancelScheduledValues(now);
    instance.gain.gain.setTargetAtTime(definition.gain, now, timeConstantFor(definition.fadeInMs ?? 300));
  }

  private teardown(id: Id, instance: LoopInstance): void {
    if (instance.timer) clearTimeout(instance.timer);
    instance.timer = null;
    try {
      instance.source.stop();
    } catch {
      // already stopped
    }
    instance.source.disconnect();
    instance.gain.disconnect();
    if (this.loops.get(id) === instance) this.loops.delete(id);
  }

  private loadBuffer(id: Id, definition: SoundDefinition): Promise<AudioBuffer | null> {
    let pending = this.buffers.get(id);
    if (!pending) {
      pending = this.fetchAndDecode(id, definition);
      this.buffers.set(id, pending);
    }
    return pending;
  }

  private async fetchAndDecode(id: Id, definition: SoundDefinition): Promise<AudioBuffer | null> {
    const ctx = this.ensureContext();
    if (!ctx) return null;
    try {
      const source = definition.sources.find((candidate) => this.env.canPlayType(candidate.type));
      if (!source) throw new Error("this browser can't play any of the available formats");
      const data = await this.env.fetchAudio(source.src);
      return await ctx.decodeAudioData(data);
    } catch (error) {
      this.env.warn(`[audio] "${id}" could not be loaded; continuing silently.`, error);
      return null;
    }
  }

  private ensureContext(): AudioContext | null {
    if (this.ctx) return this.ctx;
    if (this.contextUnavailable) return null;

    let created: AudioContext | null = null;
    try {
      created = this.env.createContext();
    } catch (error) {
      this.env.warn("[audio] Web Audio is unavailable; continuing silently.", error);
    }
    if (!created) {
      this.contextUnavailable = true;
      return null;
    }

    const ctx: AudioContext = created;
    const master = ctx.createGain();
    master.connect(ctx.destination);
    for (const channel of SOUND_CHANNELS) {
      const node = ctx.createGain();
      node.connect(master);
      this.channelGains.set(channel, node);
    }
    this.ctx = ctx;
    this.masterGain = master;
    this.applySettings(true);

    ctx.onstatechange = () => {
      if (ctx.state === "running") this.disarmGestureUnlock();
      else this.armGestureUnlock(ctx);
    };
    if (ctx.state !== "running") this.armGestureUnlock(ctx);
    return ctx;
  }

  /** Browsers may create the context "suspended" until the user has interacted; resume it on the first gesture. */
  private armGestureUnlock(ctx: AudioContext): void {
    if (this.removeGestureListener) return;
    this.removeGestureListener = this.env.onUserGesture(() => {
      ctx.resume().then(
        () => {
          if (ctx.state === "running") this.disarmGestureUnlock();
        },
        () => {}
      );
    });
  }

  private disarmGestureUnlock(): void {
    this.removeGestureListener?.();
    this.removeGestureListener = null;
  }

  private applySettings(immediate: boolean): void {
    const ctx = this.ctx;
    const master = this.masterGain;
    if (!ctx || !master) return;
    this.setGain(ctx, master.gain, this.settings.muted ? 0 : this.settings.master, immediate);
    for (const [channel, node] of this.channelGains) {
      this.setGain(ctx, node.gain, this.settings[channel], immediate);
    }
  }

  private setGain(ctx: AudioContext, param: AudioParam, value: number, immediate: boolean): void {
    const now = ctx.currentTime;
    param.cancelScheduledValues(now);
    if (immediate) param.setValueAtTime(value, now);
    else param.setTargetAtTime(value, now, SETTINGS_SMOOTHING_S);
  }
}
