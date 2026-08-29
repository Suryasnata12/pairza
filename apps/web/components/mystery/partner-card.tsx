"use client";

import { useState } from "react";
import { Flag, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { countryCodeToFlag } from "@/lib/utils";
import { useBlockUser, useReportUser } from "@/features/rewards/hooks";
import type { PartnerTeaser } from "@/types";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

const REPORT_REASONS = [
  ["harassment", "Harassment or abuse"],
  ["hate_speech", "Hate speech"],
  ["spam", "Spam"],
  ["inappropriate_content", "Inappropriate content"],
  ["impersonation", "Impersonation"],
  ["other", "Something else"],
];

export function PartnerCard({
  partner,
  partnerId,
  sessionId,
}: {
  partner: PartnerTeaser | null;
  partnerId?: string;
  sessionId: string;
}) {
  const router = useRouter();
  const blockUser = useBlockUser();
  const reportUser = useReportUser();
  const [reportOpen, setReportOpen] = useState(false);
  const [reason, setReason] = useState("harassment");
  const [details, setDetails] = useState("");

  if (!partner) return null;

  async function handleBlock() {
    if (!partnerId) return;
    if (!confirm("Block this stranger? Your current investigation will end immediately for both of you.")) return;
    try {
      await blockUser.mutateAsync(partnerId);
      toast.success("Blocked. This investigation has ended.");
      router.push("/home");
    } catch {
      toast.error("Couldn't block right now. Try again.");
    }
  }

  async function handleReport() {
    if (!partnerId) return;
    try {
      await reportUser.mutateAsync({ reported_user_id: partnerId, session_id: sessionId, reason, details });
      toast.success("Report sent. Our team will review it.");
      setReportOpen(false);
      setDetails("");
    } catch {
      toast.error("Couldn't send that report. Try again.");
    }
  }

  return (
    <div className="rounded-2xl border border-border-subtle bg-void-elevated-2/40 p-5">
      <div className="flex items-center gap-3">
        <span className="text-3xl">{countryCodeToFlag(partner.country_code)}</span>
        <div>
          <p className="font-medium text-ink">Your stranger</p>
          <p className="text-xs text-ink-faint">
            {partner.timezone_region} · {partner.puzzle_experience_level}
          </p>
        </div>
      </div>
      {partner.interests.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {partner.interests.map((interest) => (
            <span key={interest} className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-ink-muted">
              {interest}
            </span>
          ))}
        </div>
      )}
      <div className="mt-4 flex gap-2 border-t border-border-subtle pt-4">
        <Dialog open={reportOpen} onOpenChange={setReportOpen}>
          <DialogTrigger asChild>
            <Button size="sm" variant="ghost" className="flex-1">
              <Flag className="h-3.5 w-3.5" /> Report
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Report this stranger</DialogTitle>
              <DialogDescription>Your investigation continues — a moderator will review this separately.</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-3">
              <select
                className="h-11 w-full rounded-xl border border-border-subtle bg-void-elevated-2 px-4 text-sm text-ink"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              >
                {REPORT_REASONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <textarea
                className="min-h-[80px] w-full rounded-xl border border-border-subtle bg-void-elevated-2 px-4 py-3 text-sm text-ink placeholder:text-ink-faint"
                placeholder="Anything else we should know? (optional)"
                value={details}
                onChange={(e) => setDetails(e.target.value)}
              />
            </div>
            <DialogFooter>
              <Button variant="destructive" onClick={handleReport} disabled={reportUser.isPending}>
                Submit report
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <Button size="sm" variant="ghost" className="flex-1 text-urgent-coral hover:text-urgent-coral" onClick={handleBlock}>
          <ShieldAlert className="h-3.5 w-3.5" /> Block
        </Button>
      </div>
    </div>
  );
}
