import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-white">CrypSavvy</h1>
          <p className="text-muted mt-1 text-sm">Sign in to view your dashboard</p>
        </div>
        <SignIn />
      </div>
    </div>
  );
}
