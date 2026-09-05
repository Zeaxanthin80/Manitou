import type { Category } from "@/lib/api";

/**
 * The categories the site chrome shows: the top of the tree, nothing beneath.
 *
 * Top-level categories are product types -- T-Shirts, Accessories -- and that
 * is what a header and a footer are for: jeans are jeans. The level beneath is
 * the series, and it has its own places: the front-page strip, and the row of
 * links on each type's page. Listing every category flat put six series in the
 * nav and nothing a shopper would recognise as a department, which is how the
 * owner found T-Shirts empty on the first day of data entry.
 *
 * One special case, for the seeded tree. `seed.py` roots everything under a
 * single `Apparel`, and a nav with one entry is worse than none. A tree with
 * exactly one root shows that root's children instead: the types live one level
 * down, and the root is a label nobody browses by. A tree with several roots
 * shows the roots, and a flat tree shows everything, as before.
 *
 * Shared by the header and the footer so they cannot disagree about what a
 * department is.
 */
export function navCategories(all: Category[]): Category[] {
  const roots = all.filter((c) => c.parent_id === null);
  if (roots.length === 1) {
    const under = all.filter((c) => c.parent_id === roots[0].id);
    if (under.length > 0) return under;
  }
  return roots;
}
