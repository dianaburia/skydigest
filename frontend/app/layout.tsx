import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Observatory",
  description: "A weekly astronomy journal, in plain English.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
