"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Radar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { countryCodeToFlag } from "@/lib/utils";
import { CATEGORY_LABELS, type SessionDetail } from "@/types";

type Stage = "connecting" | "connection_found" | "mystery_reveal" | "clue_reveal";

const DIFFICULTY_LABELS = ["", "Gentle", "Easy", "Moderate", "Hard", "Brutal"];

export function MysteryReveal({ session, onComplete }: { session: SessionDetail; onComplete: () => void }) {
  const [stage, setStage] = useState<Stage>("connecting");

  useEffect(() => {
    const t1 = setTimeout(() => setStage("connection_found"), 1600);
    const t2 = setTimeout(() => setStage("mystery_reveal"), 3400);
    const t3 = setTimeout(() => setStage("clue_reveal"), 5200);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, []);

  const clue = session.mystery.stages[0]?.your_clue;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_50%_at_50%_50%,rgba(155,123,255,0.1),transparent)] pointer-events-none" />
      <AnimatePresence mode="wait">
        {stage === "connecting" && (
          <motion.div
            key="connecting"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-6 text-center"
          >
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }}
            >
              <Radar className="h-10 w-10 text-signal-teal" />
            </motion.div>
            <p className="font-mono text-sm uppercase tracking-[0.3em] text-ink-muted">Establishing connection…</p>
          </motion.div>
        )}

        {stage === "connection_found" && (
          <motion.div
            key="found"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{ duration: 0.5 }}
            className="flex flex-col items-center gap-4 text-center"
          >
            <span className="font-mono text-xs uppercase tracking-[0.3em] text-signal-teal">Connection found</span>
            <span className="text-7xl">{countryCodeToFlag(session.partner?.country_code ?? "")}</span>
            <p className="max-w-xs text-ink-muted">
              A stranger has entered the investigation from {session.partner?.country_code ?? "somewhere in the world"}.
            </p>
          </motion.div>
        )}

        {stage === "mystery_reveal" && (
          <motion.div
            key="mystery"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.5 }}
            className="flex flex-col items-center gap-4 text-center px-6"
          >
            <span className="font-mono text-xs uppercase tracking-[0.3em] text-signal-violet">
              {CATEGORY_LABELS[session.mystery.category] ?? session.mystery.category}
            </span>
            <h2 className="font-display text-3xl font-bold text-ink sm:text-4xl">{session.mystery.title}</h2>
            <div className="flex items-center gap-1.5">
              {[1, 2, 3, 4, 5].map((i) => (
                <span
                  key={i}
                  className={`h-2 w-2 rounded-full ${i <= session.mystery.difficulty ? "bg-signal-violet" : "bg-white/10"}`}
                />
              ))}
              <span className="ml-2 text-xs text-ink-faint">{DIFFICULTY_LABELS[session.mystery.difficulty]}</span>
            </div>
            {session.mystery.flavor_text && (
              <p className="max-w-md text-ink-muted">{session.mystery.flavor_text}</p>
            )}
          </motion.div>
        )}

        {stage === "clue_reveal" && (
          <motion.div
            key="clue"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="flex w-full max-w-lg flex-col items-center gap-6 px-6 text-center"
          >
            <span className="font-mono text-xs uppercase tracking-[0.3em] text-gold">Your clue</span>
            <div className="glass-panel w-full rounded-2xl p-8">
              <p className="text-lg leading-relaxed text-ink text-balance">{clue?.text}</p>
            </div>
            <p className="max-w-sm text-sm text-ink-faint">
              Your stranger has a different clue. Neither of you has the whole picture — yet.
            </p>
            <Button size="lg" onClick={onComplete}>
              Begin investigation <ArrowRight className="h-4 w-4" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
