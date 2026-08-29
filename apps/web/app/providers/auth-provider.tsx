"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/stores/use-auth-store";
import { api, ApiError } from "@/lib/api-client";
import type { Me } from "@/types";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const setMe = useAuthStore((s) => s.setMe);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Me>("/users/me")
      .then((me) => !cancelled && setMe(me))
      .catch((err) => {
        if (!cancelled) setMe(null);
        if (!(err instanceof ApiError)) console.error(err);
      });
    return () => {
      cancelled = true;
    };
  }, [setMe]);

  return <>{children}</>;
}

export async function refreshMe(): Promise<Me | null> {
  try {
    const me = await api.get<Me>("/users/me");
    useAuthStore.getState().setMe(me);
    return me;
  } catch {
    useAuthStore.getState().setMe(null);
    return null;
  }
}
