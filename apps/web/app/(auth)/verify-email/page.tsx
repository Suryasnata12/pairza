"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useVerifyEmail } from "@/features/auth/hooks";
import { ApiError } from "@/lib/api-client";

// `useSearchParams` opts this route out of static rendering, so it's wrapped in Suspense per
// Next's own requirement for that hook — the fallback below only flashes for a moment.
export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Card><CardContent className="py-8 text-center text-sm text-ink-muted">Loading…</CardContent></Card>}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const token = useSearchParams().get("token");
  const verifyEmail = useVerifyEmail();
  const [state, setState] = useState<"verifying" | "success" | "error">(token ? "verifying" : "error");
  const [error, setError] = useState<string | null>(token ? null : "This link is missing its token.");

  useEffect(() => {
    if (!token) return;
    verifyEmail
      .mutateAsync(token)
      .then(() => setState("success"))
      .catch((err) => {
        setState("error");
        setError(
          err instanceof ApiError && err.code === "invalid_verification_token"
            ? "This verification link is invalid or has expired."
            : "Something went wrong. Try again."
        );
      });
    // Runs once for the token in the URL — re-verifying on every render would burn the link's
    // single use against itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Verify your email</CardTitle>
        {state === "verifying" && <CardDescription>Confirming your link…</CardDescription>}
      </CardHeader>
      <CardContent>
        {state === "success" && (
          <div className="flex flex-col items-center gap-3 py-4 text-center">
            <CheckCircle2 className="h-10 w-10 text-signal-teal" />
            <p className="text-sm text-ink-muted">
              Your email is verified. Head back to Pairza to start matching with strangers.
            </p>
            <Link href="/home" className="font-medium text-signal-teal hover:underline">
              Go to Pairza
            </Link>
          </div>
        )}
        {state === "error" && (
          <div className="flex flex-col items-center gap-3 py-4 text-center">
            <XCircle className="h-10 w-10 text-urgent-coral" />
            <p className="text-sm text-ink-muted">{error}</p>
            <p className="text-sm text-ink-muted">
              You can request a new link from the{" "}
              <Link href="/home" className="font-medium text-signal-teal hover:underline">
                home screen
              </Link>{" "}
              once you're signed in.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
