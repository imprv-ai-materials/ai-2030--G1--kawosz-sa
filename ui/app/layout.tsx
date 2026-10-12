import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Jakość danych przychodu · Kawosz",
  description: "Nocna kontrola danych przychodu: dostawy, kwarantanna, koszt błędów i most przychodu.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // Rozszerzenia przeglądarki (np. LanguageTool: data-lt-installed, Grammarly) dopisują atrybuty do <html>
    // i <body>, zanim React przejmie stronę. suppressHydrationWarning wycisza tylko różnice atrybutów tych dwóch
    // elementów, a nie zawartości panelu.
    <html lang="pl" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
