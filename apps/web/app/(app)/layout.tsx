"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Flame, LayoutGrid, LogOut, ShieldCheck, Sparkles, User as UserIcon } from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useAuthStore } from "@/stores/use-auth-store";
import { useLogout } from "@/features/auth/hooks";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { countryCodeToFlag } from "@/lib/utils";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/home", label: "Today" },
  { href: "/vault", label: "Memory Vault" },
  { href: "/profile", label: "Profile" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { me, isLoading } = useAuthStore();
  const logout = useLogout();

  useEffect(() => {
    if (!isLoading && !me) router.replace("/login");
  }, [me, isLoading, router]);

  if (isLoading || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-signal-teal border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border-subtle bg-void/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-8">
            <Link href="/home" className="flex items-center gap-2 font-display text-lg font-bold tracking-tight text-ink">
              <Image src="/logo-mark.png" alt="" width={28} height={28} priority />
              Pairza
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                    pathname === link.href ? "bg-white/8 text-ink" : "text-ink-muted hover:text-ink"
                  )}
                >
                  {link.label}
                </Link>
              ))}
              {me.is_admin && (
                <Link
                  href="/admin"
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                    pathname === "/admin" ? "bg-white/8 text-ink" : "text-ink-muted hover:text-ink"
                  )}
                >
                  <ShieldCheck className="h-3.5 w-3.5" /> Admin
                </Link>
              )}
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden items-center gap-3 sm:flex">
              <span className="flex items-center gap-1 font-mono text-xs text-gold">
                <Sparkles className="h-3.5 w-3.5" /> {me.profile.xp} XP
              </span>
              {me.profile.current_streak > 0 && (
                <span className="flex items-center gap-1 font-mono text-xs text-urgent-coral">
                  <Flame className="h-3.5 w-3.5" /> {me.profile.current_streak}
                </span>
              )}
            </div>

            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button className="flex items-center gap-2 rounded-full outline-none">
                  <Avatar className="h-9 w-9 border border-border-subtle">
                    <AvatarFallback>{countryCodeToFlag(me.profile.country_code)}</AvatarFallback>
                  </Avatar>
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={8}
                  className="z-50 min-w-[200px] rounded-xl border border-border-strong bg-void-elevated p-1.5 shadow-2xl"
                >
                  <div className="px-3 py-2">
                    <p className="text-sm font-semibold text-ink">{me.profile.username}</p>
                    <p className="text-xs text-ink-faint">{me.email}</p>
                  </div>
                  <div className="my-1 h-px bg-border-subtle" />
                  <DropdownMenu.Item asChild>
                    <Link
                      href="/profile"
                      className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-muted outline-none hover:bg-white/5 hover:text-ink"
                    >
                      <UserIcon className="h-4 w-4" /> Profile
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={() => logout.mutate()}
                    className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-urgent-coral outline-none hover:bg-urgent-coral-dim"
                  >
                    <LogOut className="h-4 w-4" /> Sign out
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </div>
        <nav className="flex items-center gap-1 overflow-x-auto border-t border-border-subtle px-4 py-2 md:hidden">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap",
                pathname === link.href ? "bg-white/8 text-ink" : "text-ink-muted"
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" /> {link.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl overflow-x-hidden px-6 py-10">{children}</main>
    </div>
  );
}
