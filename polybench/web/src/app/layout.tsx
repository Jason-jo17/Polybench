import type { Metadata } from "next";
import { Schibsted_Grotesk, IBM_Plex_Mono } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";
import Navigation from "@/components/Navigation";

const sans = Schibsted_Grotesk({
  subsets: ["latin"],
  variable: "--font-schibsted",
  weight: ["400", "500", "600", "700"],
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-plex-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: { default: "PolyBench", template: "%s · PolyBench" },
  description:
    "Run coding tasks against LLMs, execute their code in a sandbox, and score the results with pass@k.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${mono.variable}`}>
        <div className="shell">
          <Navigation />
          <main className="shell-main">{children}</main>
        </div>
        <Toaster position="bottom-right" theme="system" toastOptions={{ className: "toast" }} />
      </body>
    </html>
  );
}
