"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useRegister } from "@/features/auth/hooks";
import { ApiError } from "@/lib/api-client";

const COUNTRIES = [
  ["US", "United States"], ["GB", "United Kingdom"], ["CA", "Canada"], ["AU", "Australia"],
  ["DE", "Germany"], ["FR", "France"], ["JP", "Japan"], ["KR", "South Korea"], ["BR", "Brazil"],
  ["IN", "India"], ["MX", "Mexico"], ["IT", "Italy"], ["ES", "Spain"], ["NL", "Netherlands"],
  ["SE", "Sweden"], ["PL", "Poland"], ["ZA", "South Africa"], ["NG", "Nigeria"], ["SG", "Singapore"],
  ["IE", "Ireland"], ["NZ", "New Zealand"],
];

export default function RegisterPage() {
  const router = useRouter();
  const register = useRegister();
  const [form, setForm] = useState({ email: "", password: "", username: "", country_code: "US" });
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await register.mutateAsync(form);
      router.push("/home");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>One profile. One mystery a day. No feed to scroll.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              required
              minLength={3}
              maxLength={32}
              placeholder="curious_fox"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              required
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <p className="text-xs text-ink-faint">At least 8 characters.</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="country">Country</Label>
            <select
              id="country"
              className="h-11 w-full rounded-xl border border-border-subtle bg-void-elevated-2 px-4 text-sm text-ink focus-visible:outline-none focus-visible:border-signal-teal/60"
              value={form.country_code}
              onChange={(e) => setForm({ ...form, country_code: e.target.value })}
            >
              {COUNTRIES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
            <p className="text-xs text-ink-faint">Shown to strangers as a country only — never anything more precise.</p>
          </div>
          {error && <p className="text-sm text-urgent-coral">{error}</p>}
          <Button type="submit" className="mt-2 w-full" disabled={register.isPending}>
            {register.isPending ? "Creating account…" : "Create account"}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-ink-muted">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-signal-teal hover:underline">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
