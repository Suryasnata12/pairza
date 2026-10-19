import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";
import { Analytics } from "@vercel/analytics/next";
import { QueryProvider } from "@/app/providers/query-provider";
import { AuthProvider } from "@/app/providers/auth-provider";
import { AmbienceController } from "@/components/audio/ambience-controller";
import "./globals.css";


export const metadata: Metadata = {
  metadataBase: new URL("https://pairza-inky.vercel.app"),

  title: "Pairza | Play Online Mystery Games with Strangers",

  description:
    "Play free online mystery games with Pairza. Meet a stranger, uncover clues, and solve a mystery together in a unique multiplayer experience.",

  alternates: {
    canonical: "/",
  },

  robots: {
    index: true,
    follow: true,
  },

  openGraph: {
    title: "Pairza | Play Online Mystery Games with Strangers",
    description:
      "Meet a stranger, uncover clues, and solve a mystery together in Pairza, a multiplayer online mystery game.",
    url: "https://pairza-inky.vercel.app/",
    siteName: "Pairza",
    type: "website",
  },

  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },

  manifest: "/site.webmanifest",
};


export const viewport: Viewport = {
  themeColor: "#06070b",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        {/* Loaded via classic <link> (not next/font) so the font request
            happens in the visitor's browser at runtime, not during the
            build. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-void font-body antialiased">
        <QueryProvider>
          <AuthProvider>
            {children}
            <AmbienceController />
            <Toaster
              theme="dark"
              position="top-center"
              toastOptions={{
                style: {
                  background: "#0e1018",
                  border: "1px solid rgba(255,255,255,0.1)",
                  color: "#eef0f6",
                },
              }}
            />
          </AuthProvider>
        </QueryProvider>
        <Analytics />
      </body>
    </html>
  );
}
