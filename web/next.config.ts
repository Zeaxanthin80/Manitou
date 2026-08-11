import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    /**
     * next/image refuses external hosts unless they are listed here. That is a
     * deliberate safety measure: without it, any URL stored in the database
     * could make the server fetch and re-serve arbitrary remote content.
     *
     * placehold.co is only for the seeded sample images. Phase 6 moves product
     * images to S3 + CloudFront, and that host replaces this one.
     */
    remotePatterns: [{ protocol: "https", hostname: "placehold.co" }],
  },
};

export default nextConfig;
