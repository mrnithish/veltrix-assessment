"use client";

import { AuthProvider } from "@/lib/auth";
import { PrefsProvider } from "@/lib/prefs";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <PrefsProvider>
      <AuthProvider>{children}</AuthProvider>
    </PrefsProvider>
  );
}
