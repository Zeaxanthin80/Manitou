import Image from "next/image";
import Link from "next/link";

import { listCategories, listProducts } from "@/lib/api";
import type { Category, ProductListItem } from "@/lib/api";
import { storeConfig } from "@/lib/store-config";

/**
 * One tile per series, between the hero and the grid.
 *
 * **The tree has two jobs and this is the second one.** Top-level categories are
 * product types -- T-Shirts, Accessories -- and they belong in the nav, where a
 * shopper expects to find "jeans are jeans". The level beneath is the series:
 * Field Guide, Emblem, Poster, Orbit OS. Those are what a front page shows off,
 * so the strip reads the second level and leaves the first to the header.
 *
 * This is the shape `docs/reference/catalogue-grouping.html` §03 said the
 * catalogue would need, and it needed it on the first day of data entry: the
 * owner clicked T-Shirts and found nothing, because the tree had been organised
 * by release instead. Re-nested on 2026-09-05.
 *
 * **A flat tree falls back to the top level.** A clone with no series yet still
 * gets a strip -- of its product types, which duplicates the nav but beats an
 * empty band -- and grows into the two-level shape without touching this file.
 *
 * **Everything here is derived; nothing is configured.** The tile's image is the
 * category's first product photograph and its count is the API's `total` for
 * that category, from calls the storefront already makes. No `image_url` column,
 * no `home.series[]` block: the moment a series gets its own hero shot there is a
 * second thing to update when a product changes, and §05 of that document is
 * about what that looks like six months later. First-product tiles cannot go
 * stale.
 *
 * **A category with nothing sellable hides its tile.** Mid-data-entry that is the
 * normal state, and a tile with no photograph and a count of zero reads as a
 * broken store rather than an empty shelf.
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
  const all = await listCategories();
  const series = all.filter((c) => c.parent_id !== null);
  const categories = series.length > 0 ? series : all.filter((c) => c.parent_id === null);

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
    <section aria-labelledby="series-strip-heading" className="mx-auto max-w-6xl px-6 pt-16 wide:pt-24">
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
              {/* The name underlines in muted on hover -- the nav's "you could
                  be here" gesture, not its accent "you are here" one; the
                  accent stays reserved for the current location and the
                  hero's eyebrow. Transparent-to-muted rather than
                  none-to-underline, so the text does not shift. */}
              <h3 className="mt-3 font-display text-sm uppercase leading-tight tracking-tight text-text underline decoration-transparent decoration-2 underline-offset-4 transition-[text-decoration-color] duration-300 group-hover:decoration-muted motion-reduce:transition-none">
                {category.name}
              </h3>
              {/* Same noun the catalogue heading uses. One vocabulary. */}
              <p className="mt-1 font-body text-xs uppercase tracking-wide text-muted">
                {total} {total === 1 ? "product" : "products"}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
