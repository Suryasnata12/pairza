"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { AnswerResponse, Evidence, SessionDetail } from "@/types";

export function useCurrentSession() {
  return useQuery({
    queryKey: ["session", "current"],
    queryFn: () => api.get<SessionDetail | null>("/sessions/current"),
    refetchInterval: 15000,
  });
}

export function useSession(sessionId: string | null) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.get<SessionDetail>(`/sessions/${sessionId}`),
    enabled: !!sessionId,
    refetchInterval: 20000,
  });
}

export function useSubmitAnswer(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (answer_text: string) => api.post<AnswerResponse>(`/sessions/${sessionId}/answer`, { answer_text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["session", "current"] });
      queryClient.invalidateQueries({ queryKey: ["users", "me"] });
    },
  });
}

export function useAddEvidence(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; content: string; source_url?: string }) =>
      api.post<Evidence>(`/sessions/${sessionId}/evidence`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });
}
