import Link from "next/link";
import Image from "next/image";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center px-6 py-12">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_50%_50%_at_50%_0%,rgba(155,123,255,0.12),transparent)] pointer-events-none" />
      <Link href="/" className="mb-8 flex items-center gap-2.5 font-display text-2xl font-bold tracking-tight text-ink">
        <Image src="/logo-mark.png" alt="" width={36} height={36} priority />
        Pairza
      </Link>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
