import Link from "next/link";

import { currentUser } from "@/app/actions/auth";
import { currentCart } from "@/app/actions/cart";
import { AccountMenu } from "@/components/account-menu";
import { CategoryNav } from "@/components/category-nav";
import { MobileMenu } from "@/components/mobile-menu";
import { buttonClasses } from "@/components/ui/button";
import { CartIcon } from "@/components/ui/icons";
import { Wordmark } from "@/components/ui/wordmark";
import { listCategories } from "@/lib/api";
import { navCategories } from "@/lib/categories";

/** Persistent top nav -- Section 4.3: the web expects one. Mobile gets native
 *  patterns in Phase 8, not a copy of this. */
export async function SiteHeader() {
  // Product types only -- the top of the tree. This used to list every
  // category flat, with a comment explaining that filtering to the root left a
  // one-item nav under the seeded Apparel root. Both concerns are now inside
  // navCategories(): it shows the roots, and a lone root's children in its
  // place. The series beneath the types have the front-page strip and the
  // category page's own row of links; they do not belong up here.
  const [all, user, cart] = await Promise.all([
    listCategories(),
    currentUser(),
    currentCart(),
  ]);
  const categories = navCategories(all);

  const count = cart?.item_count ?? 0;

  return (
    <header className="border-b border-border bg-surface print:hidden">
      {/* One row at every width. Below 769px the categories collapse into the
          hamburger on the left; above it they sit inline. `wide` is a custom
          769px breakpoint -- Tailwind's `md` is min-width 768px, which would
          have switched to the desktop nav AT 768 rather than below it. */}
      <nav
        aria-label="Main"
        className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-4 wide:gap-8"
      >
        <MobileMenu
          items={categories.map((c) => ({
            href: `/categories/${c.slug}`,
            label: c.name,
          }))}
          label="Categories"
          className="wide:hidden"
        />

        <Link
          href="/"
          className="shrink-0 font-display text-lg uppercase tracking-tight text-text"
        >
          <Wordmark />
        </Link>

        <div className="hidden min-w-0 overflow-x-auto wide:block">
          <CategoryNav categories={categories} />
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2 font-body text-sm wide:gap-4">
          {user ? (
            <>
              {/* Cart first, then the avatar to its right. */}
              <Link
                href="/cart"
                // The icon is aria-hidden, so the link needs its own name -- and
                // the count belongs in it. "Cart" alone would announce the same
                // thing whether it held nothing or nine items.
                aria-label={
                  count === 0
                    ? "Cart, empty"
                    : `Cart, ${count} item${count === 1 ? "" : "s"}`
                }
                className="relative flex size-9 items-center justify-center rounded-md text-text transition-colors hover:bg-background motion-reduce:transition-none"
              >
                {/* size-7, not size-6. The link box already matches the avatar's
                    36px exactly and shares its centre line -- what read as
                    "smaller" was optical: a thin outline glyph carries far less
                    weight than a solid filled circle of the same box, so the
                    glyph fills more of it to balance.

                    translate-y-0.5 nudges it 2px down. Geometrically it was
                    already centred; this is an optical correction, and the badge
                    overhanging the top-right corner is most of why it needed
                    one. A transform rather than a margin: inside an items-center
                    flex row a 2px margin-top only moves the box 1px, because the
                    margin box is what gets centred. */}
                <CartIcon className="size-7 translate-y-0.5" />
                {count > 0 && (
                  // aria-hidden because the link's own label already carries the
                  // number; announcing the badge too would say it twice.
                  <span
                    aria-hidden="true"
                    className="absolute -right-1 -top-1 flex min-w-5 items-center justify-center rounded-full bg-accent px-1 py-0.5 font-body text-xs leading-none text-surface"
                  >
                    {count > 99 ? "99+" : count}
                  </span>
                )}
              </Link>

              <AccountMenu user={user} />
            </>
          ) : (
            <>
              {/* Two links 8px apart, styled identically, read as one run of
                  text rather than two choices. Weight is what separates them:
                  "Sign in" takes a border and full-strength text, "Create
                  account" stays a plain muted link beside it.

                  buttonClasses rather than <Button>: this navigates, so it has
                  to stay an <a> -- openable in a new tab, copyable, announced as
                  a link. The helper exists for exactly that case.

                  ghost, not accent: the accent is reserved for states needing
                  attention (Section 4.3), and a permanent nav link is not one.
                  Bordered-on-transparent is also the language OrderStatus and
                  the VENDOR PORTAL badge already speak.

                  h-9 py-0 overrides the variant's py-2, which computes to 38px.
                  Every other control in this header -- hamburger, cart, avatar
                  -- is size-9. Matching 36px keeps the header exactly as tall
                  signed out as signed in, so signing in shifts nothing. */}
              <Link
                href="/login"
                className={buttonClasses({
                  variant: "ghost",
                  className: "h-9 shrink-0 py-0",
                })}
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="shrink-0 text-muted transition-colors hover:text-text motion-reduce:transition-none"
              >
                <span className="hidden sm:inline">Create account</span>
                <span className="sm:hidden">Register</span>
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
