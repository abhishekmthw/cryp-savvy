"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { navItems } from "@/components/layout/nav-items";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-60 min-h-screen border-r border-border/60 bg-card/30 backdrop-blur-xl px-3 py-6 shrink-0">
      <Link href="/" className="flex items-center gap-2.5 px-3 mb-8 group">
        <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary via-primary to-fuchsia-500 shadow-lg shadow-primary/30 transition-transform group-hover:scale-105">
          <Image
            src="/logo.svg"
            alt="CrypSavvy"
            width={26}
            height={30}
            className="h-[28px] w-auto"
            priority
          />
        </div>
        <div className="flex flex-col">
          <span className="text-base font-bold leading-none text-brand-gradient">CrypSavvy</span>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground mt-0.5">
            Trading Bot
          </span>
        </div>
      </Link>

      <nav className="flex flex-col gap-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/"
              ? pathname === "/"
              : pathname === href || pathname?.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group/link relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                active
                  ? "bg-primary/15 text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent/40 hover:text-foreground"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-primary" />
              )}
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0 transition-colors",
                  active ? "text-primary" : "group-hover/link:text-foreground"
                )}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto rounded-xl border border-border/60 bg-gradient-to-br from-primary/10 via-card to-card p-4">
        <p className="text-xs font-semibold text-foreground">Indian markets only</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          Trades INR pairs on CoinDCX. Paper mode is default — switch to live anytime in
          Dashboard.
        </p>
      </div>
    </aside>
  );
}
