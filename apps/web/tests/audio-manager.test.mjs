// Unit tests for the audio engine (lib/audio/audio-manager.ts) using a fake Web Audio implementation.
// They verify the LOGIC that decides when sound plays (single instance, no restarts, autoplay unlock,
// graceful failure, fades, volume/mute) — not how anything sounds. Run: cd apps/web && npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  AudioManager,
  DEFAULT_AUDIO_SETTINGS,
  clampVolume,
  sanitizeAudioSettings,
} from "../lib/audio/audio-manager.ts";

const flush = () => new Promise((resolve) => setImmediate(resolve));

// ---- fakes ---------------------------------------------------------------------------------------
class FakeParam {
  constructor() { this.last = undefined; this.calls = []; }
  setValueAtTime(v, t) { this.last = v; this.calls.push(["set", v, t]); }
  setTargetAtTime(v, t, tc) { this.last = v; this.calls.push(["target", v, t, tc]); }
  cancelScheduledValues(t) { this.calls.push(["cancel", t]); }
}
class FakeNode {
  constructor() { this.gain = new FakeParam(); this.connections = []; this.disconnected = false; }
  connect(node) { this.connections.push(node); }
  disconnect() { this.disconnected = true; }
}
class FakeSource {
  constructor() { this.buffer = null; this.loop = false; this.started = false; this.stopCount = 0; this.disconnected = false; this.onended = null; }
  connect() {}
  disconnect() { this.disconnected = true; }
  start() { this.started = true; }
  stop() { this.stopCount++; }
}
class FakeContext {
  constructor(state, opts) {
    this.state = state; this.opts = opts; this.currentTime = 0; this.destination = {};
    this.gains = []; this.sources = []; this.resumeCalls = 0; this.onstatechange = null;
  }
  createGain() { const g = new FakeNode(); this.gains.push(g); return g; }
  createBufferSource() { const s = new FakeSource(); this.sources.push(s); return s; }
  decodeAudioData() {
    return this.opts.decodeError ? Promise.reject(new Error("bad audio data")) : Promise.resolve({ duration: 60 });
  }
  resume() {
    this.resumeCalls++;
    return Promise.resolve().then(() => {
      if (this.opts.resumeWorks !== false) { this.state = "running"; this.onstatechange?.(); }
    });
  }
}

function makeEnv(opts = {}) {
  const ctx = new FakeContext(opts.state ?? "running", opts);
  const env = {
    contextsCreated: 0, fetches: [], warnings: [], gestureHandlers: new Set(), listenersRemoved: 0,
    createContext() {
      env.contextsCreated++;
      if (opts.throwOnCreate) throw new Error("no audio hardware");
      return opts.noContext ? null : ctx;
    },
    canPlayType: (type) => (opts.supported ?? ["audio/ogg"]).includes(type),
    async fetchAudio(url) {
      env.fetches.push(url);
      if (opts.fetchError) throw new Error("HTTP 404");
      return new ArrayBuffer(8);
    },
    onUserGesture(handler) {
      env.gestureHandlers.add(handler);
      return () => { env.gestureHandlers.delete(handler); env.listenersRemoved++; };
    },
    warn(message) { env.warnings.push(message); },
  };
  return { env, ctx };
}

const CATALOG = {
  ambience: { sources: [{ src: "/audio/ambience.ogg", type: "audio/ogg" }], channel: "music", loop: true, gain: 1, fadeInMs: 1000, fadeOutMs: 500 },
  blip: { sources: [{ src: "/audio/blip.ogg", type: "audio/ogg" }], channel: "music", loop: false, gain: 0.8 },
};
const setup = (opts) => { const { env, ctx } = makeEnv(opts); return { env, ctx, mgr: new AudioManager(CATALOG, env) }; };

// ---- settings (pure) ----------------------------------------------------------------------------
test("default ambience level is low, not muted", () => {
  assert.equal(DEFAULT_AUDIO_SETTINGS.muted, false);
  assert.ok(DEFAULT_AUDIO_SETTINGS.music > 0 && DEFAULT_AUDIO_SETTINGS.music <= 0.35);
  assert.equal(DEFAULT_AUDIO_SETTINGS.master, 1);
});

test("stored settings are sanitised: garbage falls back, numbers clamp to 0..1", () => {
  assert.deepEqual(sanitizeAudioSettings(null), DEFAULT_AUDIO_SETTINGS);
  assert.deepEqual(sanitizeAudioSettings("nope"), DEFAULT_AUDIO_SETTINGS);
  assert.deepEqual(sanitizeAudioSettings({ master: 5, music: -2, muted: "yes" }), { master: 1, music: 0, muted: false });
  assert.deepEqual(sanitizeAudioSettings({ master: 0.5, music: 0.1, muted: true }), { master: 0.5, music: 0.1, muted: true });
  assert.deepEqual(sanitizeAudioSettings({ music: NaN }), DEFAULT_AUDIO_SETTINGS);
  assert.equal(clampVolume(0.7, 0.3), 0.7);
  assert.equal(clampVolume(undefined, 0.3), 0.3);
});

// ---- looping ambience: one instance, no restarts --------------------------------------------------
test("play starts exactly one seamless looping source; repeated play() never restarts or duplicates", async () => {
  const { env, ctx, mgr } = setup();
  mgr.play("ambience");
  mgr.play("ambience"); // while still loading
  await flush();
  mgr.play("ambience"); // while playing
  mgr.play("ambience");
  await flush();

  assert.equal(ctx.sources.length, 1);
  assert.equal(ctx.sources[0].started, true);
  assert.equal(ctx.sources[0].loop, true); // sample-accurate loop, not an <audio> gap
  assert.equal(env.contextsCreated, 1);
  assert.deepEqual(env.fetches, ["/audio/ambience.ogg"]); // loaded once
  assert.equal(mgr.isPlaying("ambience"), true);
});

test("starts with a smooth fade-in from silence up to the sound's level", async () => {
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();
  const perSound = ctx.gains[2]; // master, music channel, then the per-sound node
  assert.deepEqual(perSound.gain.calls[0].slice(0, 2), ["set", 0]);
  const target = perSound.gain.calls.find((c) => c[0] === "target");
  assert.equal(target[1], 1);
  assert.ok(Math.abs(target[3] - 1 / 3) < 1e-9); // 1000 ms fade
});

test("stop() fades out, then tears the source down; playing again creates ONE fresh source from the cached buffer", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { env, ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();

  mgr.stop("ambience");
  assert.equal(mgr.isPlaying("ambience"), false);
  assert.equal(ctx.sources[0].stopCount, 0); // still fading
  t.mock.timers.tick(600);
  assert.equal(ctx.sources[0].stopCount, 1);
  assert.equal(ctx.sources[0].disconnected, true);

  mgr.play("ambience");
  await flush();
  assert.equal(ctx.sources.length, 2);
  assert.equal(mgr.isPlaying("ambience"), true);
  assert.equal(env.fetches.length, 1); // no refetch
});

test("stop then play inside the fade (React StrictMode / quick re-entry) revives the same source — no duplicate", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();

  mgr.stop("ambience");
  mgr.play("ambience");
  t.mock.timers.tick(5000); // well past the fade: the cancelled teardown must not fire
  await flush();

  assert.equal(ctx.sources.length, 1);
  assert.equal(ctx.sources[0].stopCount, 0);
  assert.equal(mgr.isPlaying("ambience"), true);
});

test("play -> stop -> play while the file is still loading yields exactly one source", async () => {
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  mgr.stop("ambience");
  mgr.play("ambience");
  await flush();
  assert.equal(ctx.sources.length, 1);
  assert.equal(mgr.isPlaying("ambience"), true);
});

test("stop() before the file finishes loading means it never starts", async () => {
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  mgr.stop("ambience");
  await flush();
  assert.equal(ctx.sources.length, 0);
  assert.equal(mgr.isPlaying("ambience"), false);
});

test("stop() on something that isn't playing is a harmless no-op", () => {
  const { mgr } = setup();
  assert.doesNotThrow(() => mgr.stop("ambience"));
  assert.doesNotThrow(() => mgr.stopAll());
});

test("stopAll stops every running loop", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();
  mgr.stopAll();
  t.mock.timers.tick(600);
  assert.equal(ctx.sources[0].stopCount, 1);
});

// ---- failing gracefully ---------------------------------------------------------------------------
test("a missing file (404) fails quietly: no throw, no sound, one warning, no retry storm", async () => {
  const { env, ctx, mgr } = setup({ fetchError: true });
  assert.doesNotThrow(() => mgr.play("ambience"));
  await flush();
  mgr.play("ambience");
  mgr.play("ambience");
  await flush();
  assert.equal(ctx.sources.length, 0);
  assert.equal(mgr.isPlaying("ambience"), false);
  assert.equal(env.warnings.length, 1);
  assert.equal(env.fetches.length, 1);
});

test("undecodable audio data fails quietly", async () => {
  const { env, ctx, mgr } = setup({ decodeError: true });
  mgr.play("ambience");
  await flush();
  assert.equal(ctx.sources.length, 0);
  assert.equal(env.warnings.length, 1);
});

test("a browser that can't play any listed format is skipped without even downloading", async () => {
  const { env, ctx, mgr } = setup({ supported: [] });
  mgr.play("ambience");
  await flush();
  assert.equal(env.fetches.length, 0);
  assert.equal(ctx.sources.length, 0);
  assert.equal(env.warnings.length, 1);
});

test("Web Audio unavailable or throwing on creation never breaks the caller", async () => {
  for (const opts of [{ noContext: true }, { throwOnCreate: true }]) {
    const { ctx, mgr } = setup(opts);
    assert.doesNotThrow(() => mgr.play("ambience"));
    await flush();
    assert.doesNotThrow(() => mgr.stop("ambience"));
    assert.doesNotThrow(() => mgr.setSettings({ ...DEFAULT_AUDIO_SETTINGS, muted: true }));
    assert.equal(ctx.sources.length, 0);
  }
});

test("server-side rendering (no window at all) is a safe no-op with the default environment", async () => {
  assert.equal(typeof window, "undefined");
  const mgr = new AudioManager(CATALOG); // real default env, but running under Node
  assert.doesNotThrow(() => mgr.play("ambience"));
  await flush();
  assert.equal(mgr.isPlaying("ambience"), false);
  assert.doesNotThrow(() => mgr.stop("ambience"));
});

// ---- autoplay policy -------------------------------------------------------------------------------
test("suspended context: playback is queued, and the first user gesture unlocks it, then stops listening", async () => {
  const { env, ctx, mgr } = setup({ state: "suspended" });
  mgr.play("ambience");
  await flush();
  mgr.play("ambience");

  assert.equal(ctx.sources.length, 1);      // created & scheduled, waiting on the browser
  assert.equal(ctx.resumeCalls, 0);         // never calls resume() outside a gesture
  assert.equal(env.gestureHandlers.size, 1); // exactly one listener, however often play() is called

  [...env.gestureHandlers][0]();             // the user clicks / taps / presses a key
  await flush();

  assert.equal(ctx.resumeCalls, 1);
  assert.equal(ctx.state, "running");
  assert.equal(env.gestureHandlers.size, 0); // listeners removed once unlocked
  assert.equal(env.listenersRemoved, 1);
  assert.equal(ctx.sources.length, 1);       // no restart, no duplicate
});

test("if a gesture isn't enough to resume yet, it keeps listening for the next one", async () => {
  const { env, ctx, mgr } = setup({ state: "suspended", resumeWorks: false });
  mgr.play("ambience");
  await flush();
  [...env.gestureHandlers][0]();
  await flush();
  assert.equal(ctx.state, "suspended");
  assert.equal(env.gestureHandlers.size, 1);
});

test("a running context (user already interacted) never registers gesture listeners", async () => {
  const { env, mgr } = setup({ state: "running" });
  mgr.play("ambience");
  await flush();
  assert.equal(env.gestureHandlers.size, 0);
});

test("if the browser later suspends the context (e.g. iOS interruption), it re-arms the unlock", async () => {
  const { env, ctx, mgr } = setup({ state: "running" });
  mgr.play("ambience");
  await flush();
  ctx.state = "suspended";
  ctx.onstatechange();
  assert.equal(env.gestureHandlers.size, 1);
});

// ---- volume / mute ----------------------------------------------------------------------------------
test("settings made before any sound exists are applied the moment audio starts", async () => {
  const { ctx, mgr } = setup();
  mgr.setSettings({ master: 0.5, music: 0.2, muted: false });
  mgr.play("ambience");
  await flush();
  const [master, music] = ctx.gains;
  assert.equal(master.gain.last, 0.5);
  assert.equal(music.gain.last, 0.2);
});

test("mute silences the master gain without stopping playback; unmute restores the master volume", async () => {
  const { ctx, mgr } = setup();
  mgr.setSettings({ master: 0.8, music: 0.3, muted: false });
  mgr.play("ambience");
  await flush();
  const master = ctx.gains[0];

  mgr.setSettings({ master: 0.8, music: 0.3, muted: true });
  assert.equal(master.gain.last, 0);
  assert.equal(mgr.isPlaying("ambience"), true); // keeps running silently, so unmute is instant and in sync

  mgr.setSettings({ master: 0.8, music: 0.3, muted: false });
  assert.equal(master.gain.last, 0.8);
});

test("master and music volumes are independent controls", async () => {
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();
  mgr.setSettings({ master: 0.4, music: 0.9, muted: false });
  assert.equal(ctx.gains[0].gain.last, 0.4);
  assert.equal(ctx.gains[1].gain.last, 0.9);
});

test("volume changes are smoothed (no clicks) once audio is running", async () => {
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();
  mgr.setSettings({ master: 0.2, music: 0.3, muted: false });
  assert.equal(ctx.gains[0].gain.calls.at(-1)[0], "target");
});

test("out-of-range volumes are clamped before they reach the audio graph", async () => {
  const { ctx, mgr } = setup();
  mgr.play("ambience");
  await flush();
  mgr.setSettings({ master: 9, music: -1, muted: false });
  assert.equal(ctx.gains[0].gain.last, 1);
  assert.equal(ctx.gains[1].gain.last, 0);
});

// ---- the extension point for future sound effects -----------------------------------------------------
test("one-shot sounds (future effects) can overlap and clean up after themselves", async () => {
  const { ctx, mgr } = setup();
  mgr.play("blip");
  mgr.play("blip");
  await flush();
  assert.equal(ctx.sources.length, 2);
  assert.ok(ctx.sources.every((s) => s.started && s.loop === false));
  ctx.sources[0].onended();
  assert.equal(ctx.sources[0].disconnected, true);
});

test("a one-shot fired before the browser is unlocked is dropped, not queued to blast out later", async () => {
  const { ctx, mgr } = setup({ state: "suspended" });
  mgr.play("blip");
  await flush();
  assert.equal(ctx.sources.length, 0);
});

test("sound effects and ambience coexist on one context", async () => {
  const { env, ctx, mgr } = setup();
  mgr.play("ambience");
  mgr.play("blip");
  await flush();
  assert.equal(env.contextsCreated, 1);
  assert.equal(ctx.sources.length, 2);
});
