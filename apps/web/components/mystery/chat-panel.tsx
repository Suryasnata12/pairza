"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useSessionSocket } from "@/lib/use-session-socket";
import { useSessionSocketStore } from "@/stores/use-session-socket-store";
import { useAuthStore } from "@/stores/use-auth-store";
import type { SessionDetail } from "@/types";

export function ChatPanel({ session }: { session: SessionDetail }) {
  const me = useAuthStore((s) => s.me);
  const { messages, partnerOnline, partnerTyping, connectionStatus } = useSessionSocketStore();
  const { sendMessage, sendTyping } = useSessionSocket(session.id);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const isTerminal = session.status !== "ACTIVE";

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, partnerTyping]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    sendMessage(draft.trim());
    setDraft("");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              partnerOnline ? "bg-signal-teal" : "bg-ink-faint",
              partnerOnline && "animate-pulse-urgent"
            )}
          />
          <span className="text-sm font-medium text-ink">Your stranger</span>
          <span className="text-xs text-ink-faint">{partnerOnline ? "online now" : "offline"}</span>
        </div>
        {connectionStatus !== "connected" && (
          <span className="text-xs text-ink-faint">{connectionStatus === "connecting" ? "connecting…" : "reconnecting…"}</span>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-2 overflow-y-auto rounded-xl border border-border-subtle bg-void-elevated-2/30 p-3">
        {messages.length === 0 && (
          <p className="py-8 text-center text-sm text-ink-faint">
            Say hello — you're about to solve something together.
          </p>
        )}
        {messages.map((msg) => {
          if (msg.type === "system" || msg.type === "partner_joined") {
            return (
              <div key={msg.id} className="py-1 text-center text-xs text-ink-faint">
                {msg.content}
              </div>
            );
          }
          if (msg.type === "discovery") {
            return (
              <div key={msg.id} className="flex items-center justify-center gap-1.5 py-1 text-center text-xs font-medium text-signal-teal">
                <Sparkles className="h-3 w-3" /> {msg.content}
              </div>
            );
          }
          const isMe = msg.sender_id === me?.id;
          return (
            <div key={msg.id} className={cn("flex", isMe ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm",
                  isMe ? "bg-signal-teal text-void" : "bg-white/8 text-ink"
                )}
              >
                {msg.content}
              </div>
            </div>
          );
        })}
        {partnerTyping && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-white/8 px-3.5 py-2 text-sm text-ink-faint">typing…</div>
          </div>
        )}
      </div>

      {!isTerminal && (
        <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
          <Input
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              sendTyping();
            }}
            placeholder="Message your stranger…"
            maxLength={2000}
          />
          <Button type="submit" size="icon" disabled={!draft.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      )}
    </div>
  );
}
