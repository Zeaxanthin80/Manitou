import Image from "next/image";
import Link from "next/link";

import { listCategories, listProducts } from "@/lib/api";
import type { Category, ProductListItem } from "@/lib/api";
import { storeConfig } from "@/lib/store-config";

/**
 * One tile per top-level category, between the hero and the grid.
 *
 * **Everything here is derived; nothing is configured.** The tile's image is the
 * category's first product photograph and its count is the API's `total` for
 * that category -- both from calls the storefront already makes. There is no
 * `categories.image_url` column, no `home.series[]` block in store config, and
 * that is a decision rather than an omission: the moment a series gets its own
 * hero shot there is a second thing to update when a product changes, and
 * `docs/reference/catalogue-grouping.html` §05 is about what that looks like six
 * months later. First-product tiles cannot go stale.
 *
 * **A category with nothing sellable hides its tile.** Mid-catalogue-entry that
 * is the normal state, and a tile with no photograph and a count of zero reads
 * as a broken store rather than an empty shelf.
 *
 * One request per category, in parallel, and `allSettled` rather than `all`: a
 * category deleted between the two calls should lose its tile, not take the
 * home page down with it.
 */

type Tile = {
  category: Category;
  total: number;
  image: NonNullable<ProductListItem["primary_image"]>;
};

async function loadTiles(): Promise<Tile[]> {
  const categories = (await listCategories()).filter((c) => c.parent_id === null);

  // The featured series leads; the rest keep the API's alphabetical order. It is
  // the one place the strip reads config, and only to decide who goes first.
  const lead = storeConfig.home.featured.category as string;
  categories.sort((a, b) => Number(b.slug === lead) - Number(a.slug === lead));

  const pages = await Promise.allSettled(
    categories.map((c) => listProducts({ category: c.slug, limit: 1 })),
  );

  const tiles: Tile[] = [];
  pages.forEach((result, i) => {
    if (result.status !== "fulfilled") return;
    const image = result.value.items[0]?.primary_image;
    if (result.value.total === 0 || !image) return;
    tiles.push({ category: categories[i], total: result.value.total, image });
  });
  return tiles;
}

export async function SeriesStrip() {
  const tiles = await loadTiles();
  if (tiles.length === 0) return null;

  return (
    <section aria-labelledby="series-strip-heading" className="mx-auto max-w-6xl px-6 pt-12">
      {/* Read by assistive tech, not shown: the tiles explain themselves, and
          the word for "a group of products" is the store's to choose --
          ImprimaPress says "series", a candle store would not. */}
      <h2 id="series-strip-heading" className="sr-only">
        Categories
      </h2>

      <ul className="grid grid-cols-2 gap-6 wide:grid-cols-4">
        {tiles.map(({ category, total, image }) => (
          <li key={category.id}>
            <Link href={`/categories/${category.slug}`} className="group block">
              <div className="relative aspect-[4/5] overflow-hidden rounded-md border border-border bg-background">
                <Image
                  src={image.url}
                  alt={image.alt_text}
                  fill
                  sizes="(min-width: 769px) 25vw, 50vw"
                  className="object-cover transition-transform group-hover:scale-[1.02] motion-reduce:transition-none"
                />
              </div>
              <h3 className="mt-3 font-display text-sm uppercase leading-tight tracking-tight text-text">
                {category.name}
              </h3>
              {/* Same noun the count line below the grid uses. One vocabulary. */}
              <p className="mt-1 font-body text-xs uppercase tracking-tight text-muted">
                {total} {total === 1 ? "product" : "products"}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
