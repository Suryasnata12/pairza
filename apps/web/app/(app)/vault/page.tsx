"use client";

import { motion } from "framer-motion";
import { CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { countryCodeToFlag, formatCountdown } from "@/lib/utils";
import { useMemories } from "@/features/rewards/hooks";

export default function VaultPage() {
  const { data: memories, isLoading } = useMemories();

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold text-ink">Memory Vault</h1>
        <p className="mt-2 text-ink-muted">Every stranger you've worked with. Every case, solved or not.</p>
      </div>

      {isLoading && (
        <div className="flex h-40 items-center justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-signal-teal border-t-transparent" />
        </div>
      )}

      {!isLoading && memories?.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
            <p className="text-ink-muted">Your vault is empty — for now.</p>
            <p className="text-sm text-ink-faint">Solve your first mystery and it'll show up here.</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {memories?.map((memory, i) => (
          <motion.div
            key={memory.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.04, 0.4) }}
          >
            <Card className="h-full overflow-hidden">
              <div className={`h-1 w-full ${memory.solved ? "bg-signal-teal" : "bg-urgent-coral"}`} />
              <CardContent className="flex flex-col gap-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-ink-faint">DAY {String(memory.day_number).padStart(3, "0")}</span>
                  {memory.solved ? (
                    <CheckCircle2 className="h-4 w-4 text-signal-teal" />
                  ) : (
                    <XCircle className="h-4 w-4 text-urgent-coral" />
                  )}
                </div>
                <h3 className="font-display font-semibold text-ink">{memory.mystery_title}</h3>
                <div className="flex items-center gap-2 text-sm text-ink-muted">
                  <span className="text-lg">{countryCodeToFlag(memory.partner_country_code)}</span>
                  <span>A stranger from {memory.partner_country_code}</span>
                </div>
                {memory.solved && memory.solve_seconds != null && (
                  <span className="font-mono text-xs text-gold">
                    Solved in {formatCountdown(memory.solve_seconds)}
                  </span>
                )}
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
