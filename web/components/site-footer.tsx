import Link from "next/link";

import { listCategories } from "@/lib/api";
import { storeConfig } from "@/lib/store-config";

/**
 * Storefront footer.
 *
 * Mounted in app/(store)/layout.tsx, so the vendor portal does not get one -- a
 * dashboard with a marketing footer is noise, and the route group already keeps
 * the two halves apart.
 *
 * Everything here comes from store config or the API. Nothing is hardcoded,
 * because a footer is exactly where store-specific copy quietly accumulates and
 * turns a clone into a find-and-replace job.
 *
 * There are deliberately no Terms/Privacy/Returns links: those pages do not
 * exist, and a footer full of dead links is worse than a short honest one. They
 * belong with the Phase 8 pre-launch pass.
 */
export async function SiteFooter() {
  const categories = await listCategories();
  // Evaluated per request. These pages are all dynamic (they read cookies), so
  // there is no build-time value to go stale in January.
  const year = new Date().getFullYear();

  return (
    // No top margin. Every page already ends with its own py-12, so an mt-24
    // here stacked on top of it and left 144px of dead space above the footer --
    // most of a phone fold. The border and the footer's own py-12 are the
    // separation; the page's padding is the gap.
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto max-w-6xl px-6 py-10">
        {/* Two columns from the narrowest screen, not one. Stacking brand,
            Shop and Help vertically made the footer 593px against 424px of
            content on a phone -- 1.4x taller than the page it supports. Side by
            side, the two short link lists cost one column's height instead of
            two. The brand block spans the full width above them. */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-8 lg:grid-cols-4">
          <div className="col-span-2">
            <p className="font-display text-lg uppercase tracking-tight text-text">
              {storeConfig.store.name}
            </p>
            <p className="mt-2 max-w-xs font-body text-sm text-muted">
              {storeConfig.store.tagline}
            </p>
            {/* Contact lives in the full-width brand block, not in the Help
                column. At 375px that column is 152px wide and the address broke
                mid-word -- "support@manitou.exa / mple". Wrapping an email
                address anywhere other than a natural boundary makes it unreadable
                and un-copyable, and no CSS property fixes that; it needs room. */}
            <a
              href={`mailto:${storeConfig.store.support_email}`}
              className="mt-4 inline-block font-body text-sm text-text transition-colors hover:text-accent motion-reduce:transition-none"
            >
              {storeConfig.store.support_email}
            </a>
          </div>

          <nav aria-labelledby="footer-shop">
            <h2
              id="footer-shop"
              className="font-body text-xs uppercase tracking-tight text-muted"
            >
              Shop
            </h2>
            <ul className="mt-3 flex flex-col gap-2">
              <li>
                <Link
                  href="/"
                  className="font-body text-sm text-text transition-colors hover:text-accent motion-reduce:transition-none"
                >
                  All products
                </Link>
              </li>
              {categories.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/categories/${c.slug}`}
                    className="font-body text-sm text-text transition-colors hover:text-accent motion-reduce:transition-none"
                  >
                    {c.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <nav aria-labelledby="footer-help">
            <h2
              id="footer-help"
              className="font-body text-xs uppercase tracking-tight text-muted"
            >
              Help
            </h2>
            <ul className="mt-3 flex flex-col gap-2">
              <li>
                <Link
                  href="/orders"
                  className="font-body text-sm text-text transition-colors hover:text-accent motion-reduce:transition-none"
                >
                  Your orders
                </Link>
              </li>
            </ul>
          </nav>
        </div>

        <p className="mt-10 border-t border-border pt-6 font-body text-xs text-muted">
          &copy; {year} {storeConfig.store.name}
        </p>
      </div>
    </footer>
  );
}
