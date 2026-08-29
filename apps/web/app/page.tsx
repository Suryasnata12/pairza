"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Compass, Globe2, KeyRound, MessagesSquare, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WorldGlobe } from "@/components/globe/world-globe";
import { useAuthStore } from "@/stores/use-auth-store";
import { CATEGORY_LABELS } from "@/types";

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  internet_hunt: Search,
  geo: Globe2,
  cipher: KeyRound,
  investigation: Compass,
  logic: Sparkles,
  pattern: Sparkles,
  visual: Sparkles,
  audio: Sparkles,
  arg: Sparkles,
};

const STEPS = [
  {
    title: "You arrive for the day",
    body: "Once every 24 hours, Pairza has something waiting for you — no feed, no scrolling, just one door in.",
  },
  {
    title: "We pair you with a stranger",
    body: "Someone else, somewhere else in the world, arriving at the same door. Neither of you chose the other.",
  },
  {
    title: "You each get half the picture",
    body: "Your clue is real, but incomplete. So is theirs. The mystery only opens all the way if you compare notes.",
  },
  {
    title: "Solve it before the connection closes",
    body: "You have 24 hours together. Then the case closes, solved or not — and tomorrow, a new door opens.",
  },
];

function ConnectorThread({ index }: { index: number }) {
  return (
    <div className="hidden md:flex items-center justify-center relative w-full h-8">
      <svg width="100%" height="32" viewBox="0 0 200 32" preserveAspectRatio="none" className="overflow-visible">
        <motion.line
          x1="0" y1="16" x2="200" y2="16"
          stroke="url(#thread-gradient)"
          strokeWidth="1.5"
          strokeDasharray="4 6"
          initial={{ pathLength: 0, opacity: 0 }}
          whileInView={{ pathLength: 1, opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: index * 0.15 }}
        />
        <defs>
          <linearGradient id="thread-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#45e8c8" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#9b7bff" stopOpacity="0.7" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const { me, isLoading } = useAuthStore();

  useEffect(() => {
    if (!isLoading && me) router.replace("/home");
  }, [me, isLoading, router]);

  return (
    <div className="relative overflow-hidden">
      {/* --- Nav --- */}
      <header className="relative z-20 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <span className="flex items-center gap-2 font-display text-xl font-bold tracking-tight text-ink">
          <Image src="/logo-mark.png" alt="" width={32} height={32} priority />
          Pairza
        </span>
        <nav className="flex items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button variant="primary" size="sm" asChild>
            <Link href="/register">Get started</Link>
          </Button>
        </nav>
      </header>

      {/* --- Hero --- */}
      <section className="relative">
        <div className="absolute inset-0 -z-10 opacity-40 [mask-image:radial-gradient(ellipse_60%_60%_at_50%_40%,black,transparent)]">
          <WorldGlobe className="h-full w-full [&>div]:h-full [&_canvas]:h-full!" />
        </div>
        <div className="mx-auto max-w-4xl px-6 pb-28 pt-16 text-center">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-white/5 px-4 py-1.5 text-xs font-mono uppercase tracking-widest text-ink-muted"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-signal-teal animate-pulse-urgent" />
            A new connection opens daily
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 font-display text-5xl font-extrabold leading-[1.05] tracking-tight text-ink sm:text-7xl text-balance"
          >
            One stranger.
            <br />
            One mystery.
            <br />
            <span className="bg-gradient-to-r from-signal-teal to-signal-violet bg-clip-text text-transparent">
              One day.
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="mx-auto mt-6 max-w-xl text-lg text-ink-muted text-balance"
          >
            Every day, Pairza pairs you with someone new, somewhere in the world. You each hold half a mystery.
            Together, for 24 hours only, you have to solve it.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row"
          >
            <Button size="lg" asChild>
              <Link href="/register">
                Meet today's stranger <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link href="/login">I already have an account</Link>
            </Button>
          </motion.div>
        </div>
      </section>

      {/* --- How it works --- */}
      <section className="relative mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-center font-display text-3xl font-bold text-ink sm:text-4xl">How it actually works</h2>
        <p className="mx-auto mt-3 max-w-lg text-center text-ink-muted">
          No profiles to browse. No swiping. Just a mystery neither of you can finish alone.
        </p>

        <div className="mt-16 grid gap-6 md:grid-cols-4 md:items-start md:gap-0">
          {STEPS.map((step, i) => (
            <div key={step.title} className="contents md:flex md:flex-col md:items-center">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                className="glass-panel flex flex-col gap-3 rounded-2xl p-6 md:h-full"
              >
                <span className="font-mono text-xs text-signal-teal">STAGE {i + 1}</span>
                <h3 className="font-display text-lg font-semibold text-ink">{step.title}</h3>
                <p className="text-sm text-ink-muted">{step.body}</p>
              </motion.div>
              {i < STEPS.length - 1 && <ConnectorThread index={i} />}
            </div>
          ))}
        </div>
      </section>

      {/* --- Categories --- */}
      <section className="relative mx-auto max-w-6xl px-6 py-24">
        <div className="glass-panel rounded-3xl p-8 sm:p-12">
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <h2 className="font-display text-3xl font-bold text-ink">Every mystery is different</h2>
              <p className="mt-2 max-w-md text-ink-muted">
                Ciphers, geography, internet archaeology, logic, pattern recognition — the format changes, the
                mechanic never does.
              </p>
            </div>
          </div>
          <div className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(CATEGORY_LABELS).map(([key, label]) => {
              const Icon = CATEGORY_ICONS[key] ?? Sparkles;
              return (
                <div
                  key={key}
                  className="flex flex-col items-center gap-3 rounded-xl border border-border-subtle bg-void-elevated-2/60 p-5 text-center transition-colors hover:border-signal-teal/40"
                >
                  <Icon className="h-5 w-5 text-signal-teal" />
                  <span className="text-sm font-medium text-ink">{label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* --- Global community --- */}
      <section className="relative mx-auto max-w-6xl px-6 py-24">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <h2 className="font-display text-3xl font-bold text-ink sm:text-4xl">
              Your stranger could be anywhere
            </h2>
            <p className="mt-4 text-ink-muted">
              Pairza connects people across time zones and countries — you'll always know roughly where your
              stranger is calling in from, and a little about their interests and experience level. Never their
              exact location, name, or any way to contact them outside the investigation.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-ink-muted">
              {[
                "Country and general timezone only — never a precise location.",
                "No usernames from other platforms, no contact details, ever.",
                "Block or report a stranger and the investigation ends immediately.",
              ].map((line) => (
                <li key={line} className="flex items-start gap-2">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-signal-teal" />
                  {line}
                </li>
              ))}
            </ul>
          </div>
          <div className="relative aspect-square">
            <WorldGlobe className="h-full w-full [&>div]:h-full [&_canvas]:h-full!" />
          </div>
        </div>
      </section>

      {/* --- Memory vault teaser --- */}
      <section className="relative mx-auto max-w-6xl px-6 py-24">
        <div className="glass-panel flex flex-col items-center gap-6 rounded-3xl p-10 text-center sm:p-16">
          <MessagesSquare className="h-8 w-8 text-signal-violet" />
          <h2 className="font-display text-3xl font-bold text-ink sm:text-4xl text-balance">
            Every solved mystery becomes a memory
          </h2>
          <p className="max-w-lg text-ink-muted">
            Your Memory Vault isn't a friends list — it's a quiet record of every stranger you've worked with, every
            case you've closed, and how far your streak has come.
          </p>
        </div>
      </section>

      {/* --- Final CTA --- */}
      <section className="relative mx-auto max-w-3xl px-6 py-24 text-center">
        <h2 className="font-display text-4xl font-bold text-ink text-balance">
          Your first stranger is already waiting.
        </h2>
        <div className="mt-8">
          <Button size="lg" asChild>
            <Link href="/register">
              Start your first mystery <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </section>

      <footer className="relative border-t border-border-subtle px-6 py-10 text-center text-sm text-ink-faint">
        Pairza — one stranger, one mystery, one day.
      </footer>
    </div>
  );
}
