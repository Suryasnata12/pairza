"use client";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/stores/use-auth-store";
import { refreshMe } from "@/app/providers/auth-provider";
import type { AuthUser } from "@/types";

interface RegisterInput {
  email: string;
  password: string;
  username: string;
  country_code: string;
}
interface LoginInput {
  email: string;
  password: string;
}

export function useRegister() {
  return useMutation({
    mutationFn: (input: RegisterInput) => api.post<AuthUser>("/auth/register", input),
    onSuccess: () => refreshMe(),
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: (input: LoginInput) => api.post<AuthUser>("/auth/login", input),
    onSuccess: () => refreshMe(),
  });
}

export function useLogout() {
  const setMe = useAuthStore((s) => s.setMe);
  return useMutation({
    mutationFn: () => api.post("/auth/logout"),
    onSuccess: () => setMe(null),
  });
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: (email: string) => api.post<{ message: string }>("/auth/forgot-password", { email }),
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (input: { token: string; new_password: string }) =>
      api.post<{ message: string }>("/auth/reset-password", input),
  });
}

export function useForgotUsername() {
  return useMutation({
    mutationFn: (username: string) => api.post<{ message: string }>("/auth/forgot-username", { username }),
  });
}
