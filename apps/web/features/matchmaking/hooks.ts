"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { MatchmakingStatus } from "@/types";

export function useMatchmakingStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["matchmaking", "status"],
    queryFn: () => api.get<MatchmakingStatus>("/matchmaking/status"),
    enabled,
    refetchInterval: (query) => (query.state.data?.status === "waiting" ? 2000 : false),
  });
}

export function useJoinMatchmaking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<MatchmakingStatus>("/matchmaking/join"),
    onSuccess: (data) => {
      queryClient.setQueryData(["matchmaking", "status"], data);
      queryClient.invalidateQueries({ queryKey: ["mysteries", "today"] });
      if (data.status === "matched") {
        queryClient.invalidateQueries({ queryKey: ["session", "current"] });
      }
    },
  });
}
