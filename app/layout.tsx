import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { NavRail } from "@/components/nav-rail";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SeaHealth | Healthcare Facility Audit System",
  description:
    "Audit and verify healthcare facility capabilities with evidence-based trust scoring for NGO planners in India.",
  keywords: ["healthcare", "audit", "facility", "trust score", "India", "NGO"],
};

export const viewport: Viewport = {
  themeColor: "#176D6A",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} bg-[var(--color-surface-canvas)]`}
    >
      <body className="antialiased">
        <NavRail />
        <main className="ml-64 min-h-screen transition-all duration-300">
          {children}
        </main>
      </body>
    </html>
  );
}
