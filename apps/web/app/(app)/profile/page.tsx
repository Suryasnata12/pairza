"use client";

import { motion } from "framer-motion";
import { Award, Flame, Globe2, Percent, Sparkles, Target } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { countryCodeToFlag, formatCountdown } from "@/lib/utils";
import { useAuthStore } from "@/stores/use-auth-store";
import { useBadges } from "@/features/rewards/hooks";
import { CATEGORY_LABELS } from "@/types";
import { cn } from "@/lib/utils";

function StatTile({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-void-elevated-2/40 p-4">
      <Icon className="h-4 w-4 text-signal-teal" />
      <span className="font-display text-xl font-bold text-ink">{value}</span>
      <span className="text-xs text-ink-faint">{label}</span>
    </div>
  );
}

export default function ProfilePage() {
  const me = useAuthStore((s) => s.me);
  const { data: badges } = useBadges();

  if (!me) return null;
  const p = me.profile;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center gap-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-signal-violet-dim text-3xl">
          {countryCodeToFlag(p.country_code)}
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold text-ink">{p.username}</h1>
          <p className="text-sm text-ink-muted">Investigator since {new Date(me.created_at).toLocaleDateString()}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile icon={Sparkles} label="Total XP" value={p.xp.toLocaleString()} />
        <StatTile icon={Target} label="Mysteries solved" value={String(p.solved_count)} />
        <StatTile icon={Percent} label="Solve rate" value={`${Math.round(p.solve_rate * 100)}%`} />
        <StatTile icon={Flame} label="Current streak" value={`${p.current_streak}d`} />
        <StatTile icon={Award} label="Longest streak" value={`${p.longest_streak}d`} />
        <StatTile icon={Globe2} label="Countries met" value={String(p.countries_encountered.length)} />
      </div>

      {p.average_solve_seconds != null && (
        <p className="text-sm text-ink-muted">
          Average solve time: <span className="font-mono text-ink">{formatCountdown(p.average_solve_seconds)}</span>
        </p>
      )}

      {p.countries_encountered.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold text-ink">Countries you've crossed paths with</h2>
          <div className="flex flex-wrap gap-2">
            {p.countries_encountered.map((code) => (
              <span key={code} className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5 text-sm">
                <span className="text-base">{countryCodeToFlag(code)}</span> {code}
              </span>
            ))}
          </div>
        </div>
      )}

      {p.categories_completed.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold text-ink">Categories completed</h2>
          <div className="flex flex-wrap gap-2">
            {p.categories_completed.map((cat) => (
              <span key={cat} className="rounded-full bg-signal-teal-dim px-3 py-1.5 text-sm text-signal-teal">
                {CATEGORY_LABELS[cat] ?? cat}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-ink">Badges</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {badges?.map((badge) => (
            <motion.div
              key={badge.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              <Card className={cn("h-full", !badge.earned && "opacity-40 grayscale")}>
                <CardContent className="flex flex-col items-center gap-2 p-5 text-center">
                  <div
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-full",
                      badge.earned ? "bg-gold-dim" : "bg-white/5"
                    )}
                  >
                    <Award className={cn("h-5 w-5", badge.earned ? "text-gold" : "text-ink-faint")} />
                  </div>
                  <p className="text-sm font-semibold text-ink">{badge.name}</p>
                  <p className="text-xs text-ink-faint">{badge.description}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
