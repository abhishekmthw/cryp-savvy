/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow images from Clerk's CDN (user avatars)
  images: {
    remotePatterns: [{ hostname: "img.clerk.com" }],
  },
};

export default nextConfig;
