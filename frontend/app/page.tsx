"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { ready, token } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready) router.replace(token ? "/chat" : "/login");
  }, [ready, token, router]);
  return null;
}
