import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/instrument-sans/latin-400.css";
import "@fontsource/instrument-sans/latin-500.css";
import "@fontsource/instrument-sans/latin-600.css";
import "@fontsource/sora/latin-500.css";
import "@fontsource/sora/latin-600.css";
import "./globals.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "StemSplitter | Find every part",
  description: "An honest audio stem separation room for producers and working musicians.",
  icons: { icon: "/favicon.svg" }
};

export const viewport: Viewport = {
  themeColor: "#07110d",
  width: "device-width",
  initialScale: 1
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
