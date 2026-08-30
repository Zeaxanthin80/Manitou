import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Build a self-contained server bundle for the container image.
   *
   * `.next/standalone` holds a minimal `server.js` plus only the node_modules
   * Next traced as reachable. Without it the image would need the whole tree --
   * 476 MB of node_modules and 798 MB of .next in this working directory.
   *
   * **It deliberately does not copy `public/` or `.next/static`.** Next's own
   * docs say so: those are expected to sit behind a CDN. The Dockerfile copies
   * them in explicitly, because they are not behind one yet (task 9 moves images
   * to CloudFront). Miss those two copies and the site still answers its health
   * check while rendering with no CSS and no images.
   */
  output: "standalone",

  /**
   * Exactly one remote host: the CloudFront distribution product photographs are
   * served from, read from the environment so a clone points at its own.
   *
   * An allow-list of ONE, not permission for https generally. It must match the
   * host in AdminImageCreate's URL validator -- the API refuses to STORE a URL
   * on any other host, and this refuses to RENDER one. Either alone leaves the
   * gap defect 1 fell through: a URL accepted by the form that then makes
   * next/image throw at render time, taking down the home page, the product page
   * and the admin edit page together.
   *
   * Empty locally, where CDN_HOST is unset and images come from public/.
   */
  images: process.env.CDN_HOST
    ? {
        remotePatterns: [
          {
            protocol: "https",
            hostname: process.env.CDN_HOST,
            pathname: "/media/**",
          },
        ],
      }
    : undefined,

  /**
   * Historical note: this file previously listed no remote patterns at all.
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
