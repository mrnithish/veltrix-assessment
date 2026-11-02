"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ChatView } from "@/components/chat/ChatView";

function ChatPageInner() {
  const params = useSearchParams();
  // "new" changes on every "New chat" click and remounts the view; "s" selects a stored conversation.
  return <ChatView key={params.get("new") ?? "chat"} sessionId={params.get("s")} prefill={params.get("q") ?? undefined} />;
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageInner />
    </Suspense>
  );
}
