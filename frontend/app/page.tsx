import { redirect } from "next/navigation";

// Root page always redirects to the dashboard.
// Clerk middleware handles unauthenticated users → /sign-in.
export default function Home() {
  redirect("/dashboard");
}
