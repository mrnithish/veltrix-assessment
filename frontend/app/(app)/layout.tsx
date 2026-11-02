"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { AppDataProvider } from "@/lib/app-data";
import { useAuth } from "@/lib/auth";

function Splash() {
  return (
    <div className="grid h-dvh place-items-center">
      <div className="flex items-center gap-2 text-[13px]"><span className="dot" /><span className="dot" style={{ animationDelay: "0.15s" }} /><span className="dot" style={{ animationDelay: "0.3s" }} /></div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { ready, token } = useAuth();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  if (!ready || !token) return <Splash />;

  return (
    <AppDataProvider>
      <div className="flex h-dvh overflow-hidden">
        <aside className="hidden w-[272px] shrink-0 border-r lg:block" style={{ borderColor: "var(--border)" }}>
          <Suspense><Sidebar /></Suspense>
        </aside>

        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
            <aside className="fade-up absolute inset-y-0 left-0 w-[280px] border-r shadow-2xl" style={{ borderColor: "var(--border)" }}>
              <Suspense><Sidebar onNavigate={() => setMobileOpen(false)} /></Suspense>
            </aside>
          </div>
        )}

        <main className="flex min-w-0 flex-1 flex-col">
          <TopBar onMenu={() => setMobileOpen(true)} />
          <div className="min-h-0 flex-1">{children}</div>
        </main>
      </div>
    </AppDataProvider>
  );
}
