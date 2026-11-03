"use client";

import { useEffect, useState } from "react";
import { BellRing, BellOff, LoaderCircle } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import {
  disablePushNotifications,
  enablePushNotifications,
  getPushSubscription,
  isPushSupported,
} from "@/lib/push-notifications";

type PreferenceResponse = {
  notifications_enabled: boolean;
  engagement_notifications_enabled: boolean;
};

export function PushNotificationSettings() {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkSetup() {
      const available = isPushSupported();
      if (!cancelled) setSupported(available);
      if (!available) return;

      if (Notification.permission === "denied") {
        await disablePushNotifications().catch(() => {});
        if (!cancelled) setEnabled(false);
        return;
      }

      try {
        const [preferences, subscription] = await Promise.all([
          api.get<PreferenceResponse>("/users/me/preferences"),
          getPushSubscription(),
        ]);

        if (!cancelled) {
          setEnabled(
            Notification.permission === "granted" &&
              Boolean(subscription) &&
              preferences.notifications_enabled &&
              preferences.engagement_notifications_enabled,
          );
        }
      } catch {
        if (!cancelled) setEnabled(false);
      }
    }

    void checkSetup();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleToggle() {
    if (busy || supported !== true) return;
    setBusy(true);

    try {
      if (enabled) {
        await disablePushNotifications();
        setEnabled(false);
        toast.success("Streak reminders and Pairza updates are disabled.");
      } else {
        await enablePushNotifications();
        setEnabled(true);
        toast.success("Streak reminders and Pairza updates are enabled.");
      }
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not update Pairza notification settings.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-signal-teal-dim">
            <BellRing className="h-5 w-5 text-signal-teal" />
          </div>
          <div>
            <h2 className="font-display text-lg font-semibold text-ink">
              Push notifications
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Manage streak reminders and occasional Pairza updates about new
              mysteries, challenges, and gameplay in one place.
            </p>
            {supported === false && (
              <p className="mt-2 text-xs text-urgent-coral">
                Push notifications are not supported in this browser context.
              </p>
            )}
            {supported && (
              <p className="mt-2 text-xs text-ink-faint">
                One account-level setting controls both notification types.
                Browser permission and an active device subscription are
                required for delivery.
              </p>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => void handleToggle()}
          disabled={busy || supported !== true}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-border-strong px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : enabled ? (
            <BellOff className="h-4 w-4" />
          ) : (
            <BellRing className="h-4 w-4" />
          )}
          {busy
            ? "Updating…"
            : enabled
              ? "Disable notifications"
              : "Enable notifications"}
        </button>
      </CardContent>
    </Card>
  );
}
