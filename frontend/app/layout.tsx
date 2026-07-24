import type { Metadata } from "next";
import { Instrument_Sans, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument-sans",
});
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Pricing Intelligence AI",
  description: "AI-driven market and competitor intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`h-full ${instrumentSans.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      <body className="h-full bg-paper text-ink antialiased">
        {/* beforeInteractive runs before hydration so the right theme
            applies immediately — avoids a flash of the wrong theme on
            load. This is the Next.js-sanctioned way to do this; a raw
            <script> tag in the React tree triggers a hydration warning. */}
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        {children}
      </body>
    </html>
  );
}
