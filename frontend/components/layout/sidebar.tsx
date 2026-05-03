"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart2, Bot, History, Zap } from "lucide-react";

const nav = [
  { href: "/dashboard", label: "Dashboard",  icon: BarChart2 },
  { href: "/trades",    label: "Trades",     icon: History    },
  { href: "/signals",   label: "Signals",    icon: Zap        },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-56 min-h-screen bg-card border-r border-border px-3 py-6 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-3 mb-8">
        <Bot className="text-accent w-6 h-6" />
        <span className="font-bold text-white text-lg">CryptoBot</span>
      </div>

      {/* Nav links */}
      <nav className="flex flex-col gap-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-accent/10 text-accent"
                  : "text-muted hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
