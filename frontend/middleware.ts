import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Public allowlist — every other route (including the dashboard at `/`)
// requires authentication. Switched from a per-route protected list because
// that approach silently failed to cover the root and was easy to drift
// from the actual routes when adding pages.
const isPublic = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
]);

export default clerkMiddleware((auth, req) => {
  if (!isPublic(req)) auth().protect();
});

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
