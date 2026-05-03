"use client";

import { UserButton } from "@clerk/nextjs";
import { BotStatus } from "@/components/dashboard/bot-status";

export function Navbar() {
  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-card shrink-0">
      <BotStatus />
      <UserButton afterSignOutUrl="/sign-in" />
    </header>
  );
}
