"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useForgotUsername } from "@/features/auth/hooks";
import { ApiError } from "@/lib/api-client";

// Pairza signs in with EMAIL, not username, so this page is for "I remember my username but
// not which email I used" — the reminder goes to that account's registered email, never shown
// here, and the response is identical whether or not the username exists (see
// auth/service.py's request_username_reminder).
export default function ForgotUsernamePage() {
  const forgotUsername = useForgotUsername();
  const [username, setUsername] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await forgotUsername.mutateAsync(username);
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Forgot your email?</CardTitle>
        <CardDescription>Enter your username and we'll email a reminder to the account on file.</CardDescription>
      </CardHeader>
      <CardContent>
        {sent ? (
          <p className="text-sm text-ink-muted">
            If that username exists, we've emailed a reminder to the email address on that account.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="username">Username</Label>
              <Input id="username" required value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            {error && <p className="text-sm text-urgent-coral">{error}</p>}
            <Button type="submit" className="mt-2 w-full" disabled={forgotUsername.isPending}>
              {forgotUsername.isPending ? "Sending…" : "Send reminder"}
            </Button>
          </form>
        )}
        <p className="mt-6 text-center text-sm text-ink-muted">
          <Link href="/login" className="font-medium text-signal-teal hover:underline">
            Back to sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
