"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useCredentials } from "@/hooks/use-api";

const EXEMPT_PREFIXES = ["/onboarding", "/settings"];

/**
 * Redirects newly-signed-up users to /onboarding when no CoinDCX credentials
 * are saved yet. Skips redirect on /onboarding and /settings so users can
 * configure or revisit those pages directly.
 */
export function OnboardingGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const { data, isLoading } = useCredentials();

  useEffect(() => {
    if (isLoading || !data) return;
    if (EXEMPT_PREFIXES.some((p) => pathname?.startsWith(p))) return;
    if (!data.coindcx.present) router.replace("/onboarding");
  }, [data, isLoading, pathname, router]);

  return null;
}
