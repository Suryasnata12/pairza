"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Badge, Memory, MysteryTeaser } from "@/types";

export function useTodaysMystery() {
  return useQuery({
    queryKey: ["mysteries", "today"],
    queryFn: () => api.get<MysteryTeaser | null>("/mysteries/today"),
  });
}

export function useBadges() {
  return useQuery({
    queryKey: ["badges"],
    queryFn: () => api.get<Badge[]>("/badges"),
  });
}

export function useMemories() {
  return useQuery({
    queryKey: ["memories"],
    queryFn: () => api.get<Memory[]>("/memories"),
  });
}

export function useBlockUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (blocked_id: string) => api.post("/blocks", { blocked_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });
}

export function useReportUser() {
  return useMutation({
    mutationFn: (input: { reported_user_id: string; session_id?: string; reason: string; details?: string }) =>
      api.post("/reports", input),
  });
}
