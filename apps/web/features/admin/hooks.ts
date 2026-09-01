"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  country_code: string;
  is_active: boolean;
  is_suspended: boolean;
  is_banned: boolean;
  is_admin: boolean;
  created_at: string;
  mystery_count: number;
  solved_count: number;
}

export interface AdminReport {
  id: string;
  reported_user_id: string;
  reason: string;
  status: string;
  created_at: string;
}

export interface AdminMystery {
  id: string;
  title: string;
  category: string;
  difficulty: number;
  summary: string;
  is_published: boolean;
  stage_count: number;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface Analytics {
  total_users: number;
  active_sessions: number;
  mysteries_completed_total: number;
  mysteries_solved_total: number;
  completion_rate: number;
  average_solve_seconds: number | null;
  category_breakdown: Record<string, number>;
  open_reports: number;
  dau: number;
  mau: number;
  d1_retention: number | null;
  d7_retention: number | null;
  d30_retention: number | null;
  matches_per_user: number;
  games_completed_per_user: number;
  average_session_length_seconds: number | null;
  dau_trend: DailyCount[];
}

export function useAdminAnalytics() {
  return useQuery({ queryKey: ["admin", "analytics"], queryFn: () => api.get<Analytics>("/admin/analytics") });
}

export function useAdminUsers(search: string) {
  return useQuery({
    queryKey: ["admin", "users", search],
    queryFn: () => api.get<AdminUser[]>(`/admin/users${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  });
}

export function useSuspendUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) =>
      api.post(`/admin/users/${userId}/suspend`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

export function useBanUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) =>
      api.post(`/admin/users/${userId}/ban`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

export function useAdminReports() {
  return useQuery({ queryKey: ["admin", "reports"], queryFn: () => api.get<AdminReport[]>("/admin/reports?status=open") });
}

export function useReviewReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, status }: { reportId: string; status: string }) =>
      api.post(`/admin/reports/${reportId}/review`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "reports"] }),
  });
}

export function useAdminMysteries() {
  return useQuery({ queryKey: ["admin", "mysteries"], queryFn: () => api.get<AdminMystery[]>("/admin/mysteries") });
}

export function useTogglePublish() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ mysteryId, publish }: { mysteryId: string; publish: boolean }) =>
      api.post(`/admin/mysteries/${mysteryId}/${publish ? "publish" : "unpublish"}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "mysteries"] }),
  });
}
