"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useResetPassword } from "@/features/auth/hooks";
import { ApiError } from "@/lib/api-client";
import { toast } from "sonner";

// `useSearchParams` opts this route out of static rendering, so it's wrapped in Suspense per
// Next's own requirement for that hook — the fallback below only flashes for a moment.
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<Card><CardContent className="py-8 text-center text-sm text-ink-muted">Loading…</CardContent></Card>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const resetPassword = useResetPassword();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!token) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Invalid link</CardTitle>
          <CardDescription>This reset link is missing its token.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-ink-muted">
            Please request a new one from{" "}
            <Link href="/forgot-password" className="font-medium text-signal-teal hover:underline">
              the password reset page
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Those passwords don't match.");
      return;
    }
    try {
      await resetPassword.mutateAsync({ token: token as string, new_password: password });
      toast.success("Password updated. Please sign in with your new password.");
      router.push("/login");
    } catch (err) {
      // The backend distinguishes an invalid/expired/already-used token here — unlike
      // forgot-password, this isn't an enumeration risk (see auth/service.py's reset_password).
      setError(
        err instanceof ApiError && err.code === "invalid_reset_token"
          ? "This reset link is invalid or has expired. Please request a new one."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong. Try again."
      );
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Choose a new password</CardTitle>
        <CardDescription>This link can only be used once.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">New password</Label>
            <Input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="confirmPassword">Confirm new password</Label>
            <Input
              id="confirmPassword"
              type="password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
          {error && (
            <p className="text-sm text-urgent-coral">
              {error}{" "}
              {error.includes("expired") && (
                <Link href="/forgot-password" className="underline">
                  Request a new link
                </Link>
              )}
            </p>
          )}
          <Button type="submit" className="mt-2 w-full" disabled={resetPassword.isPending}>
            {resetPassword.isPending ? "Updating…" : "Update password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
