"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Pin, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatRelativeTime } from "@/lib/utils";
import { useAddEvidence } from "@/features/session/hooks";
import type { SessionDetail } from "@/types";
import { useAuthStore } from "@/stores/use-auth-store";

export function EvidencePanel({ session }: { session: SessionDetail }) {
  const me = useAuthStore((s) => s.me);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const addEvidence = useAddEvidence(session.id);
  const isTerminal = session.status !== "ACTIVE";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    await addEvidence.mutateAsync({ title: title.trim(), content: content.trim() });
    setTitle("");
    setContent("");
    setOpen(false);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold text-ink">Investigation board</h2>
        {!isTerminal && (
          <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
            <Plus className="h-3.5 w-3.5" /> Pin evidence
          </Button>
        )}
      </div>

      {open && (
        <motion.form
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          onSubmit={handleSubmit}
          className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-void-elevated-2/60 p-4"
        >
          <Input placeholder="What did you find?" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Textarea
            placeholder="Details, a theory, a link your stranger should see…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={addEvidence.isPending}>
              Pin it
            </Button>
          </div>
        </motion.form>
      )}

      {session.evidence.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border-subtle p-6 text-center text-sm text-ink-faint">
          Nothing pinned yet. Anything either of you finds — a theory, a link, a hunch — belongs here.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {session.evidence.map((e) => (
            <div key={e.id} className="min-w-0 rounded-xl border border-border-subtle bg-void-elevated-2/40 p-4">
              <div className="mb-1.5 flex min-w-0 items-center gap-2">
                <Pin className="h-3.5 w-3.5 shrink-0 text-gold" />
                <span className="min-w-0 break-words font-medium text-ink">{e.title}</span>
                <span className="ml-auto shrink-0 text-xs text-ink-faint">{formatRelativeTime(e.created_at)}</span>
              </div>
              <p className="break-words text-sm text-ink-muted">{e.content}</p>
              <p className="mt-1.5 text-xs text-ink-faint">
                Pinned by {e.submitted_by === me?.id ? "you" : "your stranger"}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
