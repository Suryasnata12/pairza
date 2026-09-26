"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, type Variants } from "framer-motion";
import { ArrowRight, Compass, Radar, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MysteryReveal } from "@/components/mystery/mystery-reveal";
import { useCurrentSession } from "@/features/session/hooks";
import { useJoinMatchmaking, useMatchmakingStatus } from "@/features/matchmaking/hooks";
import { useAuthStore } from "@/stores/use-auth-store";
import { CATEGORY_LABELS } from "@/types";

function hasSeenReveal(sessionId: string): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(`pairza_revealed_${sessionId}`) === "1";
}
function markRevealSeen(sessionId: string) {
  window.localStorage.setItem(`pairza_revealed_${sessionId}`, "1");
}

export default function HomePage() {
  const router = useRouter();
  const me = useAuthStore((s) => s.me);
  const { data: session, isLoading: sessionLoading } = useCurrentSession();
  const join = useJoinMatchmaking();
  const { data: matchStatus } = useMatchmakingStatus(!session && !sessionLoading);
  const [showReveal, setShowReveal] = useState(false);

  useEffect(() => {
    if (session && session.status === "ACTIVE" && !hasSeenReveal(session.id)) {
      setShowReveal(true);
    }
  }, [session]);

  if (sessionLoading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-signal-teal border-t-transparent" />
      </div>
    );
  }

  if (showReveal && session) {
    return (
      <MysteryReveal
        session={session}
        onComplete={() => {
          markRevealSeen(session.id);
          setShowReveal(false);
          router.push(`/mystery/${session.id}`);
        }}
      />
    );
  }

  // --- Already matched, mid-investigation ---
  if (session) {
    const solvedStages = session.current_stage_number - 1;
    return (
      <div className="mx-auto max-w-xl">
        <p className="mb-8 font-mono text-xs uppercase tracking-[0.3em] text-signal-teal">Investigation in progress</p>
        <Card className="overflow-hidden">
          <div className="h-1 w-full bg-gradient-to-r from-signal-teal to-signal-violet" />
          <CardContent className="flex flex-col gap-4 p-8">
            <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
              {CATEGORY_LABELS[session.mystery.category] ?? session.mystery.category}
            </span>
            <h2 className="font-display text-2xl font-bold text-ink">{session.mystery.title}</h2>
            <p className="text-sm text-ink-muted">
              {solvedStages > 0
                ? `You and your stranger have cleared ${solvedStages} stage${solvedStages === 1 ? "" : "s"} so far.`
                : "Your investigation is waiting for you to pick it back up."}
            </p>
            <Button size="lg" className="mt-2 w-full" onClick={() => router.push(`/mystery/${session.id}`)}>
              Continue investigation <ArrowRight className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // --- Waiting for a partner ---
  if (matchStatus?.status === "waiting") {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-20 text-center">
        <motion.div animate={{ rotate: 360 }} transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }}>
          <Radar className="h-10 w-10 text-signal-teal" />
        </motion.div>
        <h2 className="font-display text-2xl font-bold text-ink">Finding your stranger…</h2>
        <p className="text-sm text-ink-muted">
          This can take a moment — you'll be paired the instant someone else is ready too.
        </p>
      </div>
    );
  }

  // --- Ready to start ---
  // One orchestrated entrance (icon, then headline, then streak badge, then button, each
  // staggered a beat after the last) rather than scattered per-element effects — after that,
  // the only motion left running is the icon's outward signal pings and the button's glow,
  // both purposeful: this is the moment Pairza is telling you a door is open right now.
  // Typed explicitly as Variants: an untyped object literal here infers `ease` as a generic
  // number[], which framer-motion's real types reject (it needs a fixed-length tuple). The
  // annotation makes TypeScript check the literal against the correct shape at declaration time.
  const ENTRANCE: Variants = {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] } },
  };

  return (
    <motion.div
      className="mx-auto flex max-w-xl flex-col items-center gap-8 py-12 text-center"
      initial="hidden"
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.12 } } }}
    >
      <motion.div variants={ENTRANCE} className="relative flex h-16 w-16 items-center justify-center">
        {/* Three outward pings at staggered delays read as one continuous signal, not three loops. */}
        <span className="absolute inset-0 rounded-2xl bg-signal-teal/40 animate-signal-ring" />
        <span className="absolute inset-0 rounded-2xl bg-signal-teal/40 animate-signal-ring [animation-delay:0.9s]" />
        <span className="absolute inset-0 rounded-2xl bg-signal-teal/40 animate-signal-ring [animation-delay:1.8s]" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-signal-teal-dim">
          <Compass className="h-8 w-8 text-signal-teal" />
        </div>
      </motion.div>
      <motion.div variants={ENTRANCE}>
        <h1 className="font-display text-3xl font-bold text-ink sm:text-4xl">
          Your next experience is ready, {me?.profile.username}.
        </h1>
        <p className="mt-3 text-ink-muted">
          Somewhere out there is a stranger about to see the same door open. Neither of you knows yet who's on the
          other side.
        </p>
      </motion.div>
      {me && me.profile.current_streak > 0 && (
        <motion.div
          variants={ENTRANCE}
          className="flex items-center gap-2 rounded-full bg-white/5 px-4 py-1.5 text-xs font-mono text-gold"
        >
          <Sparkles className="h-3.5 w-3.5" /> {me.profile.current_streak}-day streak — keep it alive
        </motion.div>
      )}
      <motion.div variants={ENTRANCE} className="relative">
        {/* A soft breathing glow behind the button — the one thing on this screen asking to be
            clicked, so it's the one thing that keeps moving once everything else has settled. */}
        <span className="absolute inset-0 -z-10 rounded-xl bg-signal-teal/50 blur-xl animate-thread-glow" />
        <Button size="lg" onClick={() => join.mutate()} disabled={join.isPending}>
          {join.isPending ? "Opening the door…" : "Enter today's mystery"} <ArrowRight className="h-4 w-4" />
        </Button>
      </motion.div>
    </motion.div>
  );
}
