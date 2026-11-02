"use client";

import { useEffect, useState } from "react";
import { BellRing, LoaderCircle } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api-client";

type PreferenceResponse = {
  engagement_notifications_enabled: boolean;
};

export function EngagementNotificationSettings() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;

    setLoadError(false);

    api
      .get<PreferenceResponse>("/users/me/preferences")
      .then((response) => {
        if (!cancelled) {
          setEnabled(response.engagement_notifications_enabled);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [retry]);

  async function handleChange(nextEnabled: boolean) {
    if (enabled === null || saving) return;

    setSaving(true);

    try {
      await api.patch("/users/me/preferences", {
        engagement_notifications_enabled: nextEnabled,
      });

      setEnabled(nextEnabled);

      toast.success(
        nextEnabled
          ? "Pairza promotional updates enabled."
          : "Pairza promotional updates disabled."
      );
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not update notification preferences."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">

        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-signal-teal-dim">
            <BellRing className="h-5 w-5 text-signal-teal" />
          </div>

          <div>
            <h2 className="font-display text-lg font-semibold text-ink">
              Promotional updates
            </h2>

            <p className="mt-1 text-sm text-ink-muted">
              Receive occasional Pairza updates about gameplay
              and new experiences.
            </p>

            <p className="mt-2 text-xs leading-relaxed text-ink-faint">
              This is optional and applies to your Pairza account.
              You can withdraw your consent at any time.
              Browser notification permission and an active device
              subscription are also required for delivery.
            </p>
          </div>
        </div>

        {loadError ? (
          <div role="alert" className="text-sm text-urgent-coral">
            Could not load your saved preference.

            <button
              type="button"
              onClick={() => setRetry((value) => value + 1)}
              className="ml-2 underline"
            >
              Retry
            </button>
          </div>
        ) : enabled === null ? (
          <div className="flex items-center gap-2 text-sm text-ink-muted">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            Loading preferences...
          </div>
        ) : (
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border-subtle bg-white/[0.03] p-4">
            <input
              type="checkbox"
              checked={enabled}
              disabled={saving}
              onChange={(event) =>
                void handleChange(event.currentTarget.checked)
              }
              className="mt-1 h-4 w-4 shrink-0 accent-teal-400"
            />

            <span className="text-sm font-medium text-ink">
              Yes, I agree to receive occasional promotional
              notifications from Pairza.
            </span>

            {saving && (
              <LoaderCircle className="ml-auto h-4 w-4 animate-spin text-signal-teal" />
            )}
          </label>
        )}

      </CardContent>
    </Card>
  );
}