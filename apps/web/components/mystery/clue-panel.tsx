"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Lock, Send, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SessionDetail } from "@/types";
import { useSubmitAnswer } from "@/features/session/hooks";
import { toast } from "sonner";

const DIFFICULTY_LABELS = ["", "Gentle", "Easy", "Moderate", "Hard", "Brutal"];

export function CluePanel({ session }: { session: SessionDetail }) {
  const [answer, setAnswer] = useState("");
  const [lastWrong, setLastWrong] = useState(false);
  const submitAnswer = useSubmitAnswer(session.id);
  const isTerminal = session.status !== "ACTIVE";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!answer.trim()) return;
    try {
      const result = await submitAnswer.mutateAsync(answer.trim());
      if (result.is_correct) {
        setLastWrong(false);
        setAnswer("");
        if (result.session_status === "SOLVED") {
          toast.success(`Case closed. +${result.xp_awarded} XP`);
        } else {
          toast.success("That's it — next stage unlocked.");
        }
      } else {
        setLastWrong(true);
        setAnswer("");
      }
    } catch {
      toast.error("Couldn't submit that answer. Try again.");
    }
  }

  const currentStage = session.mystery.stages[session.mystery.stages.length - 1];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
          {session.mystery.category.replace("_", " ")}
        </span>
        <h1 className="mt-1 font-display text-2xl font-bold text-ink">{session.mystery.title}</h1>
        <div className="mt-2 flex items-center gap-1.5">
          {[1, 2, 3, 4, 5].map((i) => (
            <span
              key={i}
              className={`h-1.5 w-1.5 rounded-full ${i <= session.mystery.difficulty ? "bg-signal-violet" : "bg-white/10"}`}
            />
          ))}
          <span className="ml-1.5 text-xs text-ink-faint">{DIFFICULTY_LABELS[session.mystery.difficulty]}</span>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {session.mystery.stages.map((stage) => (
          <motion.div
            key={stage.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl border border-border-subtle bg-void-elevated-2/50 p-5"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs uppercase tracking-wider text-signal-teal">
                Stage {stage.stage_number}
                {stage.is_final ? " · Final" : ""}
              </span>
              {stage.stage_number < session.current_stage_number && (
                <CheckCircle2 className="h-4 w-4 text-signal-teal" />
              )}
            </div>
            {stage.context && <p className="mb-3 text-sm text-ink-faint italic">{stage.context}</p>}
            <p className="text-ink leading-relaxed">{stage.your_clue?.text}</p>
          </motion.div>
        ))}

        {/* A locked placeholder for what's still ahead, without revealing anything about it. */}
        {!currentStage?.is_final && (
          <div className="flex items-center gap-3 rounded-2xl border border-dashed border-border-subtle p-5 text-ink-faint">
            <Lock className="h-4 w-4" />
            <span className="text-sm">Next stage locks until you solve this one.</span>
          </div>
        )}
      </div>

      {isTerminal ? (
        <TerminalBanner session={session} />
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <label className="font-mono text-xs uppercase tracking-widest text-ink-faint">
            {currentStage?.is_final ? "Final answer" : "Checkpoint answer"}
          </label>
          <div className="flex gap-2">
            <Input
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Type what you and your stranger think it is…"
              disabled={submitAnswer.isPending}
            />
            <Button type="submit" size="icon" disabled={submitAnswer.isPending || !answer.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
          {lastWrong && (
            <p className="flex items-center gap-1.5 text-sm text-urgent-coral">
              <XCircle className="h-3.5 w-3.5" /> Not quite it. Compare notes and try again.
            </p>
          )}
          {session.wrong_attempt_count > 0 && !lastWrong && (
            <p className="text-xs text-ink-faint">{session.wrong_attempt_count} attempt(s) so far between you two.</p>
          )}
        </form>
      )}
    </div>
  );
}

function TerminalBanner({ session }: { session: SessionDetail }) {
  if (session.status === "SOLVED") {
    return (
      <div className="rounded-2xl border border-signal-teal/30 bg-signal-teal-dim p-5 text-center">
        <CheckCircle2 className="mx-auto mb-2 h-6 w-6 text-signal-teal" />
        <p className="font-display font-semibold text-ink">Case closed.</p>
        <p className="mt-1 text-sm text-ink-muted">This one's in your Memory Vault now.</p>
      </div>
    );
  }
  const isExpired = session.status === "EXPIRED";
  return (
    <div className="rounded-2xl border border-urgent-coral/30 bg-urgent-coral-dim p-5 text-center">
      <XCircle className="mx-auto mb-2 h-6 w-6 text-urgent-coral" />
      <p className="font-display font-semibold text-ink">
        {isExpired ? "The connection expired." : "This investigation ended early."}
      </p>
      <p className="mt-1 text-sm text-ink-muted">A new one will be waiting for you.</p>
    </div>
  );
}
