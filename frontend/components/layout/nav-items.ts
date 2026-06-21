import { BarChart2, History, Settings, Wallet, Zap, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };

export const navItems: NavItem[] = [
  { href: "/",                    label: "Dashboard",  icon: BarChart2 },
  { href: "/trades",              label: "Trades",     icon: History   },
  { href: "/signals",             label: "Signals",    icon: Zap       },
  { href: "/settings/allocation", label: "Allocation", icon: Wallet    },
  { href: "/settings",            label: "Settings",   icon: Settings  },
];
