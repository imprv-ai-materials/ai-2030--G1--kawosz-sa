import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Jakość danych przychodu · Kawosz",
  description: "Nocna kontrola danych przychodu: dostawy, kwarantanna, koszt błędów i most przychodu.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}
