import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { IconSprite } from "./icons";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: "500",
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "TrendME — слабые сигналы",
  description: "Поиск зарождающихся научно-технологических трендов на основе ИИ",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${inter.variable} ${mono.variable}`}>
      <body>
        <IconSprite />
        {children}
      </body>
    </html>
  );
}
