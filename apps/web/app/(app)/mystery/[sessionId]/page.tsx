"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CountdownTimer } from "@/components/mystery/countdown-timer";
import { CluePanel } from "@/components/mystery/clue-panel";
import { EvidencePanel } from "@/components/mystery/evidence-panel";
import { ChatPanel } from "@/components/mystery/chat-panel";
import { PartnerCard } from "@/components/mystery/partner-card";
import { useSession } from "@/features/session/hooks";

export default function MysteryWorkspacePage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const { data: session, isLoading } = useSession(sessionId);

  if (isLoading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-signal-teal border-t-transparent" />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <p className="text-ink-muted">This investigation isn't available anymore.</p>
        <Link href="/home" className="text-signal-teal hover:underline">
          Back to today
        </Link>
      </div>
    );
  }

  // Partner id is included (privacy-safe: just an opaque UUID) specifically
  // so block/report have something to act on.
  const partnerId = session.partner_id ?? undefined;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <Link href="/home" className="flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Today
        </Link>
        <CountdownTimer expiresAt={session.expires_at} />
      </div>

      {/* Desktop: 3-pane layout */}
      <div className="hidden gap-6 lg:grid lg:grid-cols-[1.1fr_0.9fr_0.9fr]">
        <div className="rounded-2xl border border-border-subtle bg-void-elevated/40 p-6">
          <CluePanel session={session} />
        </div>
        <div className="rounded-2xl border border-border-subtle bg-void-elevated/40 p-6">
          <EvidencePanel session={session} />
        </div>
        <div className="flex flex-col gap-4">
          <PartnerCard partner={session.partner} partnerId={partnerId} sessionId={session.id} />
          <div className="flex-1 rounded-2xl border border-border-subtle bg-void-elevated/40 p-5" style={{ minHeight: 420 }}>
            <ChatPanel session={session} />
          </div>
        </div>
      </div>

      {/* Mobile / tablet: tabbed layout */}
      <div className="lg:hidden">
        <Tabs defaultValue="mystery">
          <TabsList className="w-full">
            <TabsTrigger value="mystery" className="flex-1">
              Mystery
            </TabsTrigger>
            <TabsTrigger value="investigate" className="flex-1">
              Investigate
            </TabsTrigger>
            <TabsTrigger value="chat" className="flex-1">
              Chat
            </TabsTrigger>
          </TabsList>
          <TabsContent value="mystery" className="rounded-2xl border border-border-subtle bg-void-elevated/40 p-5">
            <CluePanel session={session} />
          </TabsContent>
          <TabsContent value="investigate" className="rounded-2xl border border-border-subtle bg-void-elevated/40 p-5">
            <EvidencePanel session={session} />
          </TabsContent>
          <TabsContent value="chat" className="flex flex-col gap-4">
            <PartnerCard partner={session.partner} partnerId={partnerId} sessionId={session.id} />
            <div className="rounded-2xl border border-border-subtle bg-void-elevated/40 p-5" style={{ height: 420 }}>
              <ChatPanel session={session} />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
