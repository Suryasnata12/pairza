"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { MatchmakingStatus } from "@/types";

export function useMatchmakingStatus(enabled: boolean) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["matchmaking", "status"],
    queryFn: () => api.get<MatchmakingStatus>("/matchmaking/status"),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.status === "waiting" ? 2000 : false,
  });

  useEffect(() => {
    if (query.data?.status === "matched") {
      void queryClient.invalidateQueries({
        queryKey: ["session", "current"],
      });
    }
  }, [query.data?.status, queryClient]);

  return query;
}

export function useJoinMatchmaking() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<MatchmakingStatus>("/matchmaking/join"),

    onSuccess: (data) => {
      queryClient.setQueryData(["matchmaking", "status"], data);

      queryClient.invalidateQueries({
        queryKey: ["mysteries", "today"],
      });

      if (data.status === "matched") {
        queryClient.invalidateQueries({
          queryKey: ["session", "current"],
        });
      }
    },
  });
}