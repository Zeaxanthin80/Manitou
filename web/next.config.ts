import type { NextConfig } from "next";

/**
 * Content Security Policy, shipped in REPORT-ONLY mode.
 *
 * Stripe Elements mounts an iframe from js.stripe.com and talks to
 * api.stripe.com. A policy that gets those wrong does not degrade — it stops
 * customers paying, and it does so at the last step of the funnel. Report-Only
 * makes the browser evaluate the policy and complain in its console without
 * blocking anything, so the rules can be checked against a real checkout before
 * they are given teeth.
 *
 * **To finish this**: complete one test-mode purchase with the console open. If
 * nothing is reported, rename the header to `Content-Security-Policy`.
 *
 * `'unsafe-inline'` in script-src is not an oversight. The App Router injects
 * inline bootstrap scripts, and the alternative is per-request nonces, which
 * need middleware and a dynamic rendering path. Removing it is a real
 * improvement and a separate piece of work — noted rather than pretended away,
 * because a CSP with unsafe-inline stops far less XSS than it appears to.
 */
/**
 * Where presigned uploads go.
 *
 * boto3 signs virtual-hosted style with the region in the host --
 * `<bucket>.s3.<region>.amazonaws.com` -- measured against the real bucket
 * rather than assumed, because the path-style and regionless forms both exist
 * and neither would match.
 */
const s3Origin = process.env.S3_BUCKET
  ? `https://${process.env.S3_BUCKET}.s3.${process.env.S3_REGION || "us-east-1"}.amazonaws.com`
  : "";

const csp = [
  "default-src 'self'",

  // *.js.stripe.com as well as js.stripe.com: Stripe.js starts frames on
  // sibling origins where it can, and their own CSP guide lists the wildcard in
  // both script-src and frame-src. Taken from that guide rather than from what
  // a working checkout happened to request, because the origins it picks vary.
  "script-src 'self' 'unsafe-inline' https://js.stripe.com https://*.js.stripe.com",

  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob:${process.env.CDN_HOST ? ` https://${process.env.CDN_HOST}` : ""}`,

  // 'self' covers the fonts: next/font self-hosts them under
  // /_next/static/media, confirmed against the live HTML rather than assumed.
  "font-src 'self' data:",

  // fonts.googleapis.com belongs in connect-src, which reads wrong until you
  // know why: it is not a stylesheet OUR document loads. components/
  // payment-form.tsx passes a `cssSrc` to <Elements/>, and Stripe.js fetches
  // that URL itself to inject Inter into its iframe -- so it is a connection,
  // not a style. Stripe's CSP guide says exactly this. Confirmed in the browser:
  // the violation was reported against connect-src, sourced to stripe.js.
  //
  // Blocking it would not error. It would fall back to system-ui and render the
  // payment step in a different typeface from every other page, which is
  // defect 16 precisely.
  //
  // The S3 bucket is here because components/image-upload-field.tsx PUTs the
  // file straight from the browser to a presigned URL -- the API never sees the
  // bytes, which is the whole point of presigning, and which also means the
  // upload is a cross-origin connection this policy has to permit. Nothing on
  // the checkout path touches it, so testing a purchase could never have found
  // it; it was found by asking which other pages make external requests.
  //
  // Built from the bucket name rather than written out: the name is
  // account-specific and a clone has its own. Absent at build time, the entry is
  // simply omitted -- the same shape as CDN_HOST above, and the reason
  // deploy.yml verifies the built image really carries both.
  `connect-src 'self' https://api.stripe.com https://fonts.googleapis.com${s3Origin ? ` ${s3Origin}` : ""}`,

  // hooks.stripe.com is for the 3D Secure redirect. Link's hosts are absent on
  // purpose: payment-form.tsx sets `wallets: { link: "never" }`, so there is no
  // Link UI to frame, and a policy should not admit hosts the code refuses to
  // use.
  "frame-src https://js.stripe.com https://*.js.stripe.com https://hooks.stripe.com",

  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  /**
   * Tell the browser never to speak plain HTTP to this host again.
   *
   * Port 80 is not open on the load balancer, so an http:// request currently
   * fails to connect rather than being redirected. This closes the window
   * before that: the browser upgrades on its own after the first visit.
   *
   * Deliberately no `preload`. Submitting to the preload list is a commitment
   * that is slow and awkward to undo, and it belongs to a considered decision
   * rather than a config edit.
   */
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },

  /** Stop the browser guessing a content type. An uploaded file that sniffs as
   * HTML is how an image becomes a script. */
  { key: "X-Content-Type-Options", value: "nosniff" },

  /** No framing, so the storefront cannot be put inside someone else's page and
   * clicked through. Duplicated by frame-ancestors in the CSP above, which is
   * the modern form — this covers browsers that read only the old header. */
  { key: "X-Frame-Options", value: "DENY" },

  /** Send the full URL only to ourselves. Order confirmation and reset-password
   * URLs should not travel in a Referer header to a third party. */
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },

  /** This store needs none of these. Denying them means an injected script
   * cannot ask for them either.
   *
   * `payment` is deliberately absent from the list. Denying it would block the
   * Payment Request API, which is how Stripe Elements offers Apple Pay and
   * Google Pay — a wallet button that quietly stops appearing is a poor trade
   * for closing off an injected script's ability to open a payment sheet. Its
   * default of `self` already keeps it away from third-party frames. */
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },

  { key: "Content-Security-Policy-Report-Only", value: csp },
];

const nextConfig: NextConfig = {
  /**
   * Do not announce the framework and its presence in every response. Minor —
   * it narrows nobody's options for long — but it is free and there is no reason
   * to volunteer it.
   */
  poweredByHeader: false,

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },

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
