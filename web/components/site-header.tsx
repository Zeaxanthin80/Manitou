import Link from "next/link";

import { CategoryNav } from "@/components/category-nav";
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
  const categories = await listCategories();

  return (
    <header className="border-b border-border bg-surface">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-8 px-6 py-4">
        <Link
          href="/"
          className="font-display text-lg uppercase tracking-tight text-text"
        >
          {storeConfig.store.name}
        </Link>
        <CategoryNav categories={categories} />
      </nav>
    </header>
  );
}
