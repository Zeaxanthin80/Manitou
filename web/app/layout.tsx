import type { Metadata } from "next";
import { Archivo_Black, Inter } from "next/font/google";

import { SiteHeader } from "@/components/site-header";
import { storeConfig } from "@/lib/store-config";
import "./globals.css";

/* next/font self-hosts these -- the browser makes no request to Google, which
   matters for privacy and for Phase 6 where the container serves everything.
   Each exposes a CSS variable that app/tokens.css points --font-display and
   --font-body at, so the token file never needs to know how fonts are loaded.

   Archivo Black has exactly one weight (400). "Black" is the family name, not a
   weight axis -- asking for 700 makes the browser synthesise a fake bold. */
const display = Archivo_Black({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-display-family",
  display: "swap",
});

const body = Inter({
  subsets: ["latin"],
  variable: "--font-body-family",
  display: "swap",
});

export const metadata: Metadata = {
  // From store-config.json, not a literal -- a cloned store changes one file.
  title: storeConfig.store.name,
  description: `${storeConfig.store.name} online store`,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang={storeConfig.locale}>
      <body className={`${display.variable} ${body.variable}`}>
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
