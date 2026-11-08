import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/QueryProvider";
import { LenisProvider } from "@/providers/LenisProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PartProof - Blast Radius Zero Execution Console",
  description:
    "Autonomous engineering task planning, policy validation, cryptographic approval, and microVM hardware-isolated execution platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${geistSans.variable} ${geistMono.variable} min-h-screen antialiased`}
    >
      <body className="min-h-screen flex flex-col bg-[#0B0E12] text-[#F3F5F7]">
        <QueryProvider>
          <LenisProvider>{children}</LenisProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
