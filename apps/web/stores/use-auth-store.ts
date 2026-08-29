import { create } from "zustand";
import type { Me } from "@/types";

interface AuthState {
  me: Me | null;
  isLoading: boolean;
  setMe: (me: Me | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  me: null,
  isLoading: true,
  setMe: (me) => set({ me, isLoading: false }),
  setLoading: (isLoading) => set({ isLoading }),
}));
