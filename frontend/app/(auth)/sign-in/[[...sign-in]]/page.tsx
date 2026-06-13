import Image from "next/image";
import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background app-backdrop px-4">
      <div className="absolute inset-0 bg-grid opacity-30" />
      <div className="relative w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary via-primary to-fuchsia-500 shadow-lg shadow-primary/30">
            <Image
              src="/logo.svg"
              alt="CrypSavvy"
              width={32}
              height={36}
              className="h-7 w-auto"
              priority
            />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="text-brand-gradient">CrypSavvy</span>
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Sign in to view your dashboard
          </p>
        </div>
        <div className="flex justify-center">
          <SignIn forceRedirectUrl="/" signUpForceRedirectUrl="/" />
        </div>
      </div>
    </div>
  );
}
