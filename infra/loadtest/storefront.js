// A browsing customer, ramped until something breaks.
//
// Run with:  infra/scripts/loadtest.sh
//
// **This is a ramp to failure, not a pass/fail against a target.** Section 10.1
// sizes ImprimaPress at roughly ONE concurrent user at launch-day peak, and ~11
// if a post does ten times better than expected. Two Fargate tasks and a
// db.t4g.micro serve that without noticing, so "can it handle the target" would
// return green and teach nothing. The useful output is the headroom: it degrades
// at N, launch needs 1, so there are N× to spare.
//
// **Read-only, deliberately.** No cart writes, no checkout, no login. Driving
// checkout against production would create junk orders, decrement real inventory
// and fire real Stripe calls. The write path's concurrency guard is covered by
// the backend tests; a load test is the wrong instrument for it.
//
// **Think time is what makes the VU count mean "concurrent users".** Without the
// sleeps below, 100 VUs would be 100 requests in flight at all times -- which is
// not 100 people browsing, it is a denial-of-service. With ~3s of reading between
// pages, one VU approximates one person.

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const WEB = __ENV.WEB_URL || "https://imprimapress.com";
const API = __ENV.API_URL || "https://api.imprimapress.com";

const errors = new Counter("page_errors");

// The profile is chosen HERE, not on the command line. Once `scenarios` is
// defined, k6 ignores --vus and --duration entirely -- they are silently
// overridden rather than rejected, so a CLI "smoke test" would quietly run the
// full thirteen-minute ramp instead.
const SMOKE = __ENV.SMOKE === "1";

// Each level is HELD, not just touched. A ramp that only passes through a
// concurrency level cannot show a burstable instance exhausting its CPU credits,
// which is the slowest-moving failure here and the one with no alarm watching it.
const FULL_STAGES = [
  { duration: "1m", target: 10 },
  { duration: "2m", target: 10 },
  { duration: "1m", target: 50 },
  { duration: "2m", target: 50 },
  { duration: "1m", target: 100 },
  { duration: "2m", target: 100 },
  { duration: "1m", target: 200 },
  { duration: "2m", target: 200 },
  { duration: "1m", target: 0 },
];

const SMOKE_STAGES = [
  { duration: "15s", target: 5 },
  { duration: "30s", target: 5 },
  { duration: "10s", target: 0 },
];

export const options = {
  scenarios: {
    browse: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: SMOKE ? SMOKE_STAGES : FULL_STAGES,
      gracefulRampDown: "30s",
    },
  },
  // A threshold breach is the definition of "the knee". These are not SLOs; they
  // are the line past which the measurement says the system is unhappy.
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{page:catalog}": ["p(95)<800"],
    "http_req_duration{page:product}": ["p(95)<800"],
    "http_req_duration{page:api_health}": ["p(95)<300"],
  },
  // The summary that matters, rather than k6's default percentiles.
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
};

// Slugs are discovered, never hardcoded: a script that browses made-up URLs
// measures the 404 path, which is fast and proves nothing about the catalogue.
export function setup() {
  const p = http.get(`${API}/products?limit=50`);
  const c = http.get(`${API}/categories`);
  if (p.status !== 200 || c.status !== 200) {
    throw new Error(`setup failed: products=${p.status} categories=${c.status}`);
  }
  const products = JSON.parse(p.body).items.map((i) => i.slug);
  const categories = JSON.parse(c.body).map((i) => i.slug);
  if (products.length === 0) {
    throw new Error("no products in the catalogue -- nothing to browse");
  }
  console.log(`  discovered ${products.length} products, ${categories.length} categories`);
  return { products, categories };
}

const pick = (a) => a[Math.floor(Math.random() * a.length)];

export default function (data) {
  // 1. Land on the catalogue. Every visitor does this.
  let res = http.get(`${WEB}/`, { tags: { page: "catalog" } });
  if (!check(res, { "catalog 200": (r) => r.status === 200 })) errors.add(1);
  sleep(2 + Math.random() * 2);

  // 2. Most people open a product.
  if (Math.random() < 0.7) {
    res = http.get(`${WEB}/products/${pick(data.products)}`, { tags: { page: "product" } });
    if (!check(res, { "product 200": (r) => r.status === 200 })) errors.add(1);
    sleep(3 + Math.random() * 3);
  }

  // 3. Some browse a category.
  if (data.categories.length && Math.random() < 0.3) {
    res = http.get(`${WEB}/categories/${pick(data.categories)}`, { tags: { page: "category" } });
    if (!check(res, { "category 200": (r) => r.status === 200 })) errors.add(1);
    sleep(2 + Math.random() * 2);
  }

  // 4. A cheap API probe on every iteration, so application latency can be told
  //    apart from load-balancer and network latency. /health is one SELECT 1.
  res = http.get(`${API}/health`, { tags: { page: "api_health" } });
  if (!check(res, { "health 200": (r) => r.status === 200 })) errors.add(1);
}
