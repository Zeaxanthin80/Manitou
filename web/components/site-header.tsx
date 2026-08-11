import Link from "next/link";

import { currentUser } from "@/app/actions/auth";
import { currentCart } from "@/app/actions/cart";
import { AccountMenu } from "@/components/account-menu";
import { CategoryNav } from "@/components/category-nav";
import { MobileMenu } from "@/components/mobile-menu";
import { CartIcon } from "@/components/ui/icons";
import { listCategories } from "@/lib/api";
import { storeConfig } from "@/lib/store-config";

/** Persistent top nav -- Section 4.3: the web expects one. Mobile gets native
 *  patterns in Phase 7, not a copy of this. */
export async function SiteHeader() {
  // Every category, not just top-level. The seeded tree is Apparel ->
  // {T-Shirts, Accessories}, so filtering to parent_id === null left a nav with
  // a single item and no way to reach the categories a shopper actually browses.
  // A deeper tree would want dropdowns or a sub-nav on the category page; at two
  // levels, flat is the honest answer.
  const [categories, user, cart] = await Promise.all([
    listCategories(),
    currentUser(),
    currentCart(),
  ]);

  const count = cart?.item_count ?? 0;

  return (
    <header className="border-b border-border bg-surface">
      {/* One row at every width. Below 769px the categories collapse into the
          hamburger on the left; above it they sit inline. `wide` is a custom
          769px breakpoint -- Tailwind's `md` is min-width 768px, which would
          have switched to the desktop nav AT 768 rather than below it. */}
      <nav
        aria-label="Main"
        className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-4 wide:gap-8"
      >
        <MobileMenu categories={categories} />

        <Link
          href="/"
          className="shrink-0 font-display text-lg uppercase tracking-tight text-text"
        >
          {storeConfig.store.name}
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
                <CartIcon className="size-6" />
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
              <Link
                href="/login"
                className="shrink-0 text-muted transition-colors hover:text-text motion-reduce:transition-none"
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
