"use client";

import { UserButton } from "@clerk/nextjs";
import { usePathname } from "next/navigation";

import { BotStatus } from "@/components/dashboard/bot-status";
import { MobileNav } from "@/components/layout/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { Separator } from "@/components/ui/separator";

const titles: Record<string, { title: string; subtitle: string }> = {
  "/":           { title: "Dashboard",      subtitle: "Live portfolio overview" },
  "/trades":     { title: "Trade History",  subtitle: "Every completed trade" },
  "/signals":    { title: "Signal Scanner", subtitle: "Latest market analysis" },
  "/settings":   { title: "Settings",       subtitle: "Manage API credentials" },
  "/onboarding": { title: "Welcome",        subtitle: "Set up your bot in two steps" },
};

export function Navbar() {
  const pathname = usePathname() ?? "/";
  const matched = titles[pathname] ?? titles["/"];

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-border/60 bg-background/70 px-4 backdrop-blur-xl md:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <MobileNav />
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold text-foreground md:text-base">
            {matched.title}
          </h1>
          <p className="truncate text-xs text-muted-foreground">{matched.subtitle}</p>
        </div>
      </div>

      <div className="flex items-center gap-2 md:gap-3">
        <BotStatus />
        <Separator orientation="vertical" className="hidden h-6 md:block" />
        <ThemeToggle />
        <UserButton afterSignOutUrl="/sign-in" />
      </div>
    </header>
  );
}
