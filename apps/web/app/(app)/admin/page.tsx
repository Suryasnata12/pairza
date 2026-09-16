"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from "recharts";
import { Ban, Search, ShieldOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthStore } from "@/stores/use-auth-store";
import {
  useAdminAnalytics,
  useAdminMysteries,
  useAdminReports,
  useAdminUsers,
  useBanUser,
  useCategoryConfigs,
  useGenerationStatus,
  useReviewReport,
  useSuspendUser,
  useToggleCategory,
  useTogglePublish,
  useTriggerGeneration,
} from "@/features/admin/hooks";
import { CATEGORY_LABELS } from "@/types";
import { formatCountdown } from "@/lib/utils";

export default function AdminPage() {
  const router = useRouter();
  const me = useAuthStore((s) => s.me);

  useEffect(() => {
    if (me && !me.is_admin) router.replace("/home");
  }, [me, router]);

  if (!me?.is_admin) return null;

  return (
    <div className="flex flex-col gap-8">
      <h1 className="font-display text-3xl font-bold text-ink">Admin</h1>
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="mysteries">Mysteries</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab />
        </TabsContent>
        <TabsContent value="users">
          <UsersTab />
        </TabsContent>
        <TabsContent value="mysteries">
          <MysteriesTab />
        </TabsContent>
        <TabsContent value="reports">
          <ReportsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="font-display text-2xl font-bold text-ink">{value}</p>
        <p className="mt-1 text-xs text-ink-faint">{label}</p>
        {hint && <p className="mt-1 text-[11px] text-ink-faint/70">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function retentionLabel(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-ink-faint">{children}</h2>;
}

function OverviewTab() {
  const { data } = useAdminAnalytics();
  if (!data) return null;

  const chartData = Object.entries(data.category_breakdown).map(([key, value]) => ({
    name: CATEGORY_LABELS[key] ?? key,
    count: value,
  }));

  const trendData = data.dau_trend.map((d) => ({
    date: new Date(d.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    count: d.count,
  }));

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <SectionHeading>Users</SectionHeading>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatCard label="Total users" value={data.total_users.toLocaleString()} />
          <StatCard label="Active sessions" value={String(data.active_sessions)} />
          <StatCard label="Open reports" value={String(data.open_reports)} />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <SectionHeading>Daily engagement</SectionHeading>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="DAU" value={String(data.dau)} hint="active today" />
          <StatCard label="MAU" value={String(data.mau)} hint="active in last 30 days" />
          <StatCard label="D1 retention" value={retentionLabel(data.d1_retention)} hint={data.d1_retention == null ? "not enough data yet" : "back the next day"} />
          <StatCard label="D7 retention" value={retentionLabel(data.d7_retention)} hint={data.d7_retention == null ? "not enough data yet" : "back after a week"} />
          <StatCard label="D30 retention" value={retentionLabel(data.d30_retention)} hint={data.d30_retention == null ? "not enough data yet" : "still around after a month"} />
        </div>
        {trendData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Daily active users — last 30 days</CardTitle>
            </CardHeader>
            <CardContent className="h-56 p-4 pt-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" stroke="#9498ad" fontSize={11} tickLine={false} interval={4} />
                  <YAxis stroke="#9498ad" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "#0e1018", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }} />
                  <Line type="monotone" dataKey="count" stroke="#45e8c8" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <SectionHeading>Gameplay</SectionHeading>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <StatCard label="Matches / user" value={data.matches_per_user.toFixed(1)} />
          <StatCard label="Games completed / user" value={data.games_completed_per_user.toFixed(1)} />
          <StatCard
            label="Avg. session length"
            value={data.average_session_length_seconds != null ? formatCountdown(data.average_session_length_seconds) : "—"}
            hint="match to solved/failed/expired"
          />
          <StatCard label="Completion rate" value={`${Math.round(data.completion_rate * 100)}%`} />
          <StatCard label="Solved total" value={String(data.mysteries_solved_total)} />
          <StatCard label="Completed total" value={String(data.mysteries_completed_total)} />
        </div>
        {data.average_solve_seconds != null && (
          <p className="text-sm text-ink-muted">
            Average <span className="text-ink-faint">solve</span> time (successful only):{" "}
            <span className="font-mono text-ink">{formatCountdown(data.average_solve_seconds)}</span>
          </p>
        )}
        {chartData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Completions by category</CardTitle>
            </CardHeader>
            <CardContent className="h-64 p-4 pt-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" stroke="#9498ad" fontSize={11} tickLine={false} />
                  <YAxis stroke="#9498ad" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "#0e1018", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }} />
                  <Bar dataKey="count" fill="#45e8c8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function UsersTab() {
  const [search, setSearch] = useState("");
  const { data: users } = useAdminUsers(search);
  const suspend = useSuspendUser();
  const ban = useBanUser();

  return (
    <div className="flex flex-col gap-4">
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
        <Input placeholder="Search by email or username" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="overflow-x-auto rounded-xl border border-border-subtle">
        <table className="w-full text-sm">
          <thead className="border-b border-border-subtle bg-white/5 text-left text-xs uppercase text-ink-faint">
            <tr>
              <th className="p-3">User</th>
              <th className="p-3">Stats</th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id} className="border-b border-border-subtle last:border-0">
                <td className="p-3">
                  <p className="font-medium text-ink">{u.username}</p>
                  <p className="text-xs text-ink-faint">{u.email}</p>
                </td>
                <td className="p-3 text-ink-muted">
                  {u.solved_count}/{u.mystery_count} solved
                </td>
                <td className="p-3">
                  {u.is_banned ? (
                    <Badge variant="coral">Banned</Badge>
                  ) : u.is_suspended ? (
                    <Badge variant="gold">Suspended</Badge>
                  ) : (
                    <Badge variant="teal">Active</Badge>
                  )}
                </td>
                <td className="p-3">
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={u.is_banned}
                      onClick={() => suspend.mutate({ userId: u.id, reason: "Admin action" })}
                    >
                      <ShieldOff className="h-3.5 w-3.5" /> Suspend
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-urgent-coral hover:text-urgent-coral"
                      disabled={u.is_banned}
                      onClick={() => {
                        if (confirm(`Ban ${u.username}? This is a serious action.`)) {
                          ban.mutate({ userId: u.id, reason: "Admin action" });
                        }
                      }}
                    >
                      <Ban className="h-3.5 w-3.5" /> Ban
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MysteriesTab() {
  const { data: mysteries } = useAdminMysteries();
  const togglePublish = useTogglePublish();

  return (
    <div className="flex flex-col gap-8">
      <CategoryPoolSection />
      <div className="overflow-x-auto rounded-xl border border-border-subtle">
        <table className="w-full text-sm">
          <thead className="border-b border-border-subtle bg-white/5 text-left text-xs uppercase text-ink-faint">
            <tr>
              <th className="p-3">Title</th>
              <th className="p-3">Category</th>
              <th className="p-3">Difficulty</th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {mysteries?.map((m) => (
              <tr key={m.id} className="border-b border-border-subtle last:border-0">
                <td className="p-3 font-medium text-ink">{m.title}</td>
                <td className="p-3 text-ink-muted">{CATEGORY_LABELS[m.category] ?? m.category}</td>
                <td className="p-3 text-ink-muted">{m.difficulty}/5</td>
                <td className="p-3">
                  <Badge variant={m.is_published ? "teal" : "default"}>{m.is_published ? "Published" : "Draft"}</Badge>
                </td>
                <td className="p-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => togglePublish.mutate({ mysteryId: m.id, publish: !m.is_published })}
                  >
                    {m.is_published ? "Unpublish" : "Publish"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CategoryPoolSection() {
  const { data } = useCategoryConfigs();
  const toggleCategory = useToggleCategory();
  const [genCategory, setGenCategory] = useState<string>("");
  const [genAll, setGenAll] = useState(false);
  const [genQuantity, setGenQuantity] = useState(5);
  const triggerGeneration = useTriggerGeneration();
  const { data: jobStatus } = useGenerationStatus(true);
  const isRunning = jobStatus?.status === "running";

  async function handleGenerate() {
    if (!genAll && !genCategory) return;
    await triggerGeneration.mutateAsync({
      category: genAll ? undefined : genCategory,
      all_categories: genAll,
      quantity: genQuantity,
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <SectionHeading>Mystery pool by category</SectionHeading>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {data?.categories.map((c) => (
          <Card key={c.category}>
            <CardContent className="flex flex-col gap-2 p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-ink">{CATEGORY_LABELS[c.category] ?? c.category}</span>
                <Badge variant={c.is_enabled ? "teal" : "coral"}>{c.is_enabled ? "On" : "Off"}</Badge>
              </div>
              <p className="text-xs text-ink-faint">
                {c.published_count} published · {c.draft_count} draft
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => toggleCategory.mutate({ category: c.category, isEnabled: !c.is_enabled })}
              >
                {c.is_enabled ? "Disable" : "Enable"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Generate more mysteries</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 pt-0">
          <p className="text-xs text-ink-faint">
            Runs the AI generation pipeline (structural + duplicate + semantic validation) and saves only what
            passes. Requires ANTHROPIC_API_KEY to be configured on the server — see .env.example.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-sm text-ink-muted">
              <input type="checkbox" checked={genAll} onChange={(e) => setGenAll(e.target.checked)} />
              All categories
            </label>
            {!genAll && (
              <select
                className="h-9 rounded-lg border border-border-subtle bg-void-elevated-2 px-3 text-sm text-ink"
                value={genCategory}
                onChange={(e) => setGenCategory(e.target.value)}
              >
                <option value="">Choose a category…</option>
                {data?.categories.map((c) => (
                  <option key={c.category} value={c.category}>
                    {CATEGORY_LABELS[c.category] ?? c.category}
                  </option>
                ))}
              </select>
            )}
            <Input
              type="number"
              min={1}
              max={50}
              value={genQuantity}
              onChange={(e) => setGenQuantity(Number(e.target.value))}
              className="w-24"
            />
            <Button size="sm" onClick={handleGenerate} disabled={isRunning || (!genAll && !genCategory)}>
              {isRunning ? "Generating…" : "Generate"}
            </Button>
          </div>

          {jobStatus && jobStatus.status !== "idle" && (
            <div className="mt-2 rounded-lg border border-border-subtle bg-void-elevated-2/40 p-3 text-xs">
              <p className="font-medium text-ink">
                {jobStatus.status === "running" && "Generating — this can take a while, one AI call per attempt…"}
                {jobStatus.status === "done" && "Last run finished:"}
                {jobStatus.status === "failed" && `Failed: ${jobStatus.error}`}
              </p>
              {jobStatus.report?.map((r) => (
                <div key={r.category} className="mt-1 text-ink-muted">
                  <span className="font-mono">{r.category}</span>: requested {r.requested}, attempts {r.attempts},
                  rejected {r.rejected}, saved {r.saved}
                  {r.rejections.length > 0 && (
                    <ul className="ml-4 list-disc text-ink-faint">
                      {r.rejections.slice(0, 5).map((reason, i) => (
                        <li key={i}>{reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ReportsTab() {
  const { data: reports } = useAdminReports();
  const review = useReviewReport();

  if (reports?.length === 0) {
    return <p className="py-12 text-center text-ink-muted">No open reports. All clear.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {reports?.map((r) => (
        <Card key={r.id}>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="font-medium text-ink capitalize">{r.reason.replace("_", " ")}</p>
              <p className="text-xs text-ink-faint">{new Date(r.created_at).toLocaleString()}</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => review.mutate({ reportId: r.id, status: "dismissed" })}>
                Dismiss
              </Button>
              <Button size="sm" variant="destructive" onClick={() => review.mutate({ reportId: r.id, status: "actioned" })}>
                Action taken
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
