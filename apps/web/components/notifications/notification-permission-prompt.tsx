
"use client";

import { useCallback, useEffect, useState } from "react";
import { BellRing, LoaderCircle, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  disablePushNotifications,
  enablePushNotifications,
  getPushSubscription,
  isPushSupported,
} from "@/lib/push-notifications";

type NotificationPermissionPromptProps = {
  userId: string;
};

const DISMISSED_KEY_PREFIX = "pairza:notification-prompt-dismissed:";

export function NotificationPermissionPrompt({
  userId,
}: NotificationPermissionPromptProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [permission, setPermission] =
    useState<NotificationPermission | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dismissedKey = `${DISMISSED_KEY_PREFIX}${userId}`;

  useEffect(() => {
    let cancelled = false;

    async function checkNotificationSetup() {
      setOpen(false);
      setError(null);

      if (!isPushSupported()) return;

      const currentPermission = Notification.permission;
      setPermission(currentPermission);

      // A browser-level block disables both notification categories for this account.
      if (currentPermission === "denied") {
        void disablePushNotifications().catch(() => {});
        return;
      }

      // Respect dismissal for the rest of this browser session.
      try {
        if (window.sessionStorage.getItem(dismissedKey) === "1") {
          return;
        }
      } catch {
        // Storage may be unavailable in private or restricted contexts.
      }

      try {
        const [subscription, preferences] = await Promise.all([
          getPushSubscription(),
          api.get<{
            notifications_enabled: boolean;
            engagement_notifications_enabled: boolean;
          }>("/users/me/preferences"),
        ]);

        if (cancelled) return;

        const alreadyEnabled =
          Boolean(subscription) &&
          preferences.notifications_enabled &&
          preferences.engagement_notifications_enabled;

        if (alreadyEnabled) return;

        setOpen(true);
      } catch {
        // If checking the existing subscription fails, allow the user
        // to retry setup through the existing subscription helper.
        if (!cancelled) {
          setOpen(true);
        }
      }
    }

    void checkNotificationSetup();

    return () => {
      cancelled = true;
    };
  }, [dismissedKey]);

  const dismissPrompt = useCallback(() => {
    try {
      window.sessionStorage.setItem(dismissedKey, "1");
    } catch {
      // The dialog can still be dismissed if storage is unavailable.
    }

    // Maybe later is an opt-out; both categories remain disabled.
    void disablePushNotifications().catch(() => {});
    setOpen(false);
  }, [dismissedKey]);

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      dismissPrompt();
      return;
    }

    setOpen(true);
  }

  async function handleAllowNotifications() {
    if (busy) return;

    setBusy(true);
    setError(null);

    try {
      // This is called directly from the user's click handler.
      // The helper requests browser permission, registers the service
      // worker, subscribes to PushManager, and saves the subscription
      // through the existing authenticated API endpoint.
      await enablePushNotifications();

      setPermission("granted");
      setOpen(false);

      try {
        window.sessionStorage.removeItem(dismissedKey);
      } catch {
        // Successful subscription does not depend on session storage.
      }

      toast.success("Streak reminders and Pairza updates are enabled.");
    } catch (cause) {
      const message =
        cause instanceof Error
          ? cause.message
          : "Could not set up Pairza notifications.";

      if (
        isPushSupported() &&
        Notification.permission === "denied"
      ) {
        await disablePushNotifications().catch(() => {});
        setPermission("denied");
        setOpen(false);

        toast.error(
          "Notifications are blocked. Streak reminders and Pairza updates are disabled."
        );
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  if (!isPushSupported()) return null;
  if (permission === "denied") return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md p-6 sm:p-8">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-signal-teal-dim">
          <BellRing className="h-7 w-7 text-signal-teal" />
        </div>

        <DialogHeader className="items-center text-center">
          <DialogTitle className="text-xl sm:text-2xl">
            {permission === "granted"
              ? "Finish setting up notifications"
              : "Stay connected with Pairza"}
          </DialogTitle>

          <DialogDescription className="mt-2 text-center leading-relaxed">
            {permission === "granted"
              ? "Your browser allows notifications, but Pairza still needs to finish setting up reminders on this device."
              : "Get reminders when your streak is at risk, plus occasional Pairza updates about new mysteries, challenges, and gameplay."}
          </DialogDescription>
        </DialogHeader>

        <div className="mt-3 flex items-start gap-3 rounded-xl border border-border-subtle bg-white/[0.03] p-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-signal-teal" />
          <p className="text-xs leading-relaxed text-ink-muted">
            Enabling notifications turns on both streak reminders and
            promotional Pairza updates. You can turn both off anytime
            from your Profile.
          </p>
        </div>

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-urgent-coral-dim p-3 text-sm text-urgent-coral"
          >
            {error}
          </p>
        )}

        <DialogFooter className="mt-6 flex-col gap-2 sm:flex-col">
          <Button
            type="button"
            className="w-full"
            disabled={busy}
            onClick={() => void handleAllowNotifications()}
          >
            {busy ? (
              <>
                <LoaderCircle className="h-4 w-4 animate-spin" />
                Setting up...
              </>
            ) : permission === "granted" ? (
              "Finish setup"
            ) : (
              "Enable notifications"
            )}
          </Button>

          <Button
            type="button"
            variant="ghost"
            className="w-full"
            disabled={busy}
            onClick={dismissPrompt}
          >
            Maybe later
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
