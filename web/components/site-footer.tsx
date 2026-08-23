import Link from "next/link";

import { Wordmark } from "@/components/ui/wordmark";
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

/**
 * One treatment for every section label, so the three subsections are visibly
 * the same rank.
 *
 * This inverts what was here before. The labels were 12px/400/muted sitting on
 * top of 14px/400/text links -- smaller, lighter and no heavier than the items
 * they introduced, losing to their own children on all three axes at once. That
 * is why the footer read as one flat list with two grey lines in it rather than
 * as three groups.
 *
 * The label wins on colour and weight instead of on size: small, wide-tracked
 * caps in full-strength text read as a different KIND of text -- a label -- not
 * as a smaller heading. The rule underneath is what actually draws the boundary,
 * and it lands on the same border token as the footer's own top edge.
 *
 * tracking-wide, not tracking-tight. Negative tracking suits the big display
 * wordmark; on 12px caps it closes up letterforms that are already cramped, and
 * the old value was pulling them 0.3px tighter.
 */
const sectionLabel =
  "border-b border-border pb-2 font-body text-xs font-medium uppercase tracking-wide text-text";

/** Links now rest muted and brighten on hover, so they sit UNDER their label
 *  rather than shouting over it. #57534E on white is 7.6:1 -- comfortably past
 *  AA, so receding here costs no legibility. */
const footerLink =
  "font-body text-sm text-muted transition-colors hover:text-accent motion-reduce:transition-none";
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
        <div className="grid grid-cols-2 gap-x-6 gap-y-10 lg:grid-cols-4">
          <div className="col-span-2">
            <p className="font-display text-lg uppercase tracking-tight text-text">
              <Wordmark />
            </p>
            <p className="mt-2 max-w-xs font-body text-sm text-muted">
              {storeConfig.store.tagline}
            </p>
            {/* Contact lives in the full-width brand block, not in the Help
                column. At 375px that column is 152px wide and the address broke
                mid-word -- "support@manitou.exa / mple". Wrapping an email
                address anywhere other than a natural boundary makes it unreadable
                and un-copyable, and no CSS property fixes that; it needs room.

                max-w-xs ties this label's rule to the tagline's measure. Not to
                the other two rules -- measured, it is 320px against their 258px
                at 1280 and 152px at 375, so it is the longest of the three at
                every width. That is correct rather than sloppy: the brand block
                really is wider than a column, and on a phone it really does span
                both. What max-w-xs prevents is the rule running the full 540px
                of the two-column block, at which point it stops reading as a
                section label and starts reading as a page divider. */}
            <div className="mt-6 max-w-xs">
              {/* No id: unlike Shop and Help this is not a <nav>, so nothing
                  points an aria-labelledby at it. */}
              <h2 className={sectionLabel}>Contact</h2>
              <a
                href={`mailto:${storeConfig.store.support_email}`}
                // Stays full-strength while the nav links recede: it is the one
                // thing in here a stuck customer needs to find.
                className="mt-4 inline-block font-body text-sm text-text transition-colors hover:text-accent motion-reduce:transition-none"
              >
                {storeConfig.store.support_email}
              </a>
            </div>
          </div>

          <nav aria-labelledby="footer-shop">
            <h2 id="footer-shop" className={sectionLabel}>
              Shop
            </h2>
            {/* mt-4, not mt-3: the label now owns a rule, so the list has to
                clear the rule rather than the text. */}
            <ul className="mt-4 flex flex-col gap-2">
              <li>
                <Link href="/" className={footerLink}>
                  All products
                </Link>
              </li>
              {categories.map((c) => (
                <li key={c.id}>
                  <Link href={`/categories/${c.slug}`} className={footerLink}>
                    {c.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <nav aria-labelledby="footer-help">
            <h2 id="footer-help" className={sectionLabel}>
              Help
            </h2>
            <ul className="mt-4 flex flex-col gap-2">
              <li>
                <Link href="/orders" className={footerLink}>
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
