import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * No `images.remotePatterns` on purpose.
   *
   * next/image refuses external hosts unless they are listed, which is a real
   * safety measure: without it, any URL stored in the database could make the
   * server fetch and re-serve arbitrary remote content. Product images are now
   * served from web/public/, so no host needs that trust.
   *
   * Phase 6 moves images to S3 + CloudFront and adds that one host here.
   */
};

export default nextConfig;
