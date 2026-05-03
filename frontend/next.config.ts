import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow images from Clerk's CDN (user avatars)
  images: {
    remotePatterns: [{ hostname: "img.clerk.com" }],
  },
};

export default nextConfig;
