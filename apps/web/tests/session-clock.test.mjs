// Unit tests for the countdown's timing math (lib/session-clock.ts).
//
// Zero dependencies: Node's built-in test runner + Node's TypeScript type stripping.
//   cd apps/web && npm test          (needs Node >= 22.6)
//
// This file is plain .mjs on purpose, so `next build`'s TypeScript pass (which only includes
// .ts/.tsx) never sees it.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clockOffsetMs,
  displaySeconds,
  formatTimeLimit,
  remainingMs,
  urgencyFor,
} from "../lib/session-clock.ts";

const MIN = 60_000;
const SERVER_NOW = Date.parse("2026-09-20T12:00:00.000Z");

/** What the browser computes from one API response, given the device clock at the moment it arrived. */
function viewOf(session, deviceNowAtReceipt, deviceNowLater) {
  const offset = clockOffsetMs(session.server_time, deviceNowAtReceipt);
  return remainingMs(session.expires_at, deviceNowLater, offset);
}

test("a fresh 5-minute session reads 5:00, not 4:59", () => {
  const session = { server_time: "2026-09-20T12:00:00Z", expires_at: "2026-09-20T12:05:00Z" };
  const ms = viewOf(session, SERVER_NOW, SERVER_NOW);
  assert.equal(ms, 5 * MIN);
  assert.equal(displaySeconds(ms), 300);
  assert.equal(displaySeconds(ms - 1), 300); // still 5:00 for the first millisecond
  assert.equal(displaySeconds(ms - 1000), 299);
});

test("two players with WRONG device clocks see the same remaining time", () => {
  const session = { server_time: "2026-09-20T12:00:00Z", expires_at: "2026-09-20T12:15:00Z" }; // 15 min left

  // Player A's laptop clock is 7 minutes fast, player B's phone is 3 minutes slow.
  const aReceipt = SERVER_NOW + 7 * MIN;
  const bReceipt = SERVER_NOW - 3 * MIN;

  // Both look at the timer 90 seconds after their response arrived.
  const a = displaySeconds(viewOf(session, aReceipt, aReceipt + 90_000));
  const b = displaySeconds(viewOf(session, bReceipt, bReceipt + 90_000));

  assert.equal(a, 15 * 60 - 90);
  assert.equal(a, b);
});

test("the naive device-clock approach would have disagreed (documents why the offset exists)", () => {
  const expiresMs = Date.parse("2026-09-20T12:15:00Z");
  const naiveA = expiresMs - (SERVER_NOW + 7 * MIN); // device 7 min fast
  const naiveB = expiresMs - (SERVER_NOW - 3 * MIN); // device 3 min slow
  assert.notEqual(naiveA, naiveB);
  assert.equal(naiveB - naiveA, 10 * MIN);
});

test("a page refresh does not reset the timer: the same deadline keeps counting down", () => {
  const expires_at = "2026-09-20T12:10:00Z";
  // First load at 12:00:00.
  const first = viewOf({ server_time: "2026-09-20T12:00:00Z", expires_at }, 1_000, 1_000);
  // Reload 4 minutes later — the server sends a NEW server_time but the SAME expires_at.
  const reloaded = viewOf({ server_time: "2026-09-20T12:04:00Z", expires_at }, 9_999_000, 9_999_000);
  assert.equal(first, 10 * MIN);
  assert.equal(reloaded, 6 * MIN); // not 10 minutes again
});

test("remaining time never goes negative and hits exactly zero at the deadline", () => {
  const session = { server_time: "2026-09-20T12:00:00Z", expires_at: "2026-09-20T12:05:00Z" };
  assert.equal(viewOf(session, SERVER_NOW, SERVER_NOW + 5 * MIN), 0);
  assert.equal(viewOf(session, SERVER_NOW, SERVER_NOW + 5 * MIN + 1), 0);
  assert.equal(viewOf(session, SERVER_NOW, SERVER_NOW + 30 * MIN), 0);
  assert.equal(displaySeconds(0), 0);
  assert.equal(displaySeconds(-5000), 0);
  assert.equal(displaySeconds(1), 1); // 1 ms left still shows 0:01 until the deadline passes
});

test("parses the microsecond-precision ISO strings the API actually sends", () => {
  const session = { server_time: "2026-09-20T12:00:00.123456+00:00", expires_at: "2026-09-20T12:05:00.123456+00:00" };
  const ms = viewOf(session, 42, 42);
  assert.equal(ms, 5 * MIN);
});

test("unparseable timestamps fall back safely instead of producing NaN", () => {
  assert.equal(clockOffsetMs("not a date", 123), 0);
  assert.equal(remainingMs("not a date", 123, 0), 0);
});

test("urgency follows the server-provided warning window (5-minute session: last 60s)", () => {
  assert.equal(urgencyFor(300, 60), "normal"); // a brand-new 5-minute session is NOT urgent
  assert.equal(urgencyFor(61, 60), "normal");
  assert.equal(urgencyFor(60, 60), "urgent");
  assert.equal(urgencyFor(31, 60), "urgent");
  assert.equal(urgencyFor(30, 60), "critical");
  assert.equal(urgencyFor(0, 60), "critical");
});

test("urgency scales for a 30-minute session (last 6 minutes)", () => {
  assert.equal(urgencyFor(1800, 360), "normal");
  assert.equal(urgencyFor(361, 360), "normal");
  assert.equal(urgencyFor(360, 360), "urgent");
  assert.equal(urgencyFor(180, 360), "critical");
});

test("time limits render for every tier the API can send", () => {
  const seconds = [300, 600, 900, 1200, 1800];
  assert.deepEqual(seconds.map(formatTimeLimit), ["5 min", "10 min", "15 min", "20 min", "30 min"]);
  assert.equal(formatTimeLimit(3600), "1 hr");
  assert.equal(formatTimeLimit(5400), "1 hr 30 min");
  assert.equal(formatTimeLimit(null), "—");
  assert.equal(formatTimeLimit(undefined), "—");
});
