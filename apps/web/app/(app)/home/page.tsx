"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
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
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-8 py-12 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-signal-teal-dim">
        <Compass className="h-8 w-8 text-signal-teal" />
      </div>
      <div>
        <h1 className="font-display text-3xl font-bold text-ink sm:text-4xl">
          Your next experience is ready, {me?.profile.username}.
        </h1>
        <p className="mt-3 text-ink-muted">
          Somewhere out there is a stranger about to see the same door open. Neither of you knows yet who's on the
          other side.
        </p>
      </div>
      {me && me.profile.current_streak > 0 && (
        <div className="flex items-center gap-2 rounded-full bg-white/5 px-4 py-1.5 text-xs font-mono text-gold">
          <Sparkles className="h-3.5 w-3.5" /> {me.profile.current_streak}-day streak — keep it alive
        </div>
      )}
      <Button size="lg" onClick={() => join.mutate()} disabled={join.isPending}>
        {join.isPending ? "Opening the door…" : "Enter today's mystery"} <ArrowRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
