import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tax Filing Assistant",
  description: "LLM-powered tax filing assistant with tool calling",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
