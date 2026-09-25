import type { Metadata } from "next";
import { Space_Grotesk, DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Navigation from "@/components/Navigation";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["300", "400", "500", "600", "700"],
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["300", "400", "500", "600"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "PolyBench — AI Coding Benchmark Harness",
  description: "Evaluate frontier LLMs on real programming tasks with sandbox execution, pass@k scoring, and failure taxonomy analysis.",
};

import { Toaster } from "sonner";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${spaceGrotesk.variable} ${dmSans.variable} ${jetbrainsMono.variable} pb-layout-body`}
      >
        <Navigation />
        <main className="pb-layout-main">
          {children}
        </main>
        <Toaster position="top-right" theme="dark" toastOptions={{ className: 'pb-toast-custom' }} />
      </body>
    </html>
  );
}
