import Image from "next/image";
import Link from "next/link";

import { buttonClasses } from "@/components/ui/button";
import { storeConfig } from "@/lib/store-config";

/**
 * The one series the store is leading with, above the catalogue grid.
 *
 * **Every word of it comes from store-config.json.** A headline, a subhead and
 * a button label are store voice in exactly the way `store.tagline` is, and the
 * config file's own notes make that argument already: a clone selling candles
 * must not edit a component to change what it says. The only thing this file
 * decides is the shape.
 *
 * **It links to a category, not to a hand-kept list.** `GET /products?category=`
 * already filters recursively over the category subtree, so the series page is
 * the category page -- no new endpoint, no `featured` column, no second place
 * where the membership of a series is recorded and can drift from the first.
 *
 * The lead photograph is named in config rather than derived from the featured
 * category's first product. Deriving looks tidier and is worse: it hands a
 * merchandising decision to whichever product happens to sort first
 * alphabetically, and it rules out ever leading with a shot that is not a
 * product image.
 */
export function FeaturedSeries() {
  // Widened from the generated `as const` literals on purpose. store-config.ts
  // is generated from the JSON, so `category` types as its current value and a
  // literal-typed check would read as always-true to the compiler while being
  // the actual switch at runtime.
  const featured: {
    category: string;
    eyebrow: string;
    heading: string;
    body: string;
    cta: string;
    image: string;
    image_alt: string;
  } = storeConfig.home.featured;

  // Empty category means "not leading with anything" -- the band disappears and
  // the home page is the plain catalogue it was before. Same convention as
  // `store.logo`: the key stays, the value empties. Deleting the block instead
  // would be a compile error, which is the louder and less useful failure.
  if (!featured.category) return null;

  return (
    <section
      aria-labelledby="featured-series"
      className="mt-12 grid gap-8 wide:grid-cols-[22rem_1fr] wide:items-center wide:gap-12"
    >
      {/* Fixed 4:5 box with object-cover, the same frame the catalogue tiles
          use. A band whose height changed with whichever photograph is current
          would shift everything below it on every merchandising change. */}
      <div className="relative aspect-[4/5] overflow-hidden rounded-md border border-border bg-background">
        <Image
          src={featured.image}
          alt={featured.image_alt}
          fill
          sizes="(min-width: 769px) 22rem, 100vw"
          // The largest thing above the fold, so it is the LCP element on the
          // busiest page in the store. Worth the preload hint.
          priority
          className="object-cover"
        />
      </div>

      <div>
        {/* Merchandising is what the accent token is documented for. It is used
            once here and once in the nav to mark the current category -- two
            places on a page, which is the ceiling for it. */}
        <p className="font-body text-xs uppercase tracking-tight text-accent">
          {featured.eyebrow}
        </p>
        <h2
          id="featured-series"
          className="mt-3 font-display text-2xl uppercase leading-none tracking-tight text-text"
        >
          {featured.heading}
        </h2>
        <p className="mt-4 max-w-prose font-body text-base text-muted">
          {featured.body}
        </p>
        <Link
          href={`/categories/${featured.category}`}
          className={buttonClasses({ className: "mt-8 inline-flex" })}
        >
          {featured.cta}
        </Link>
      </div>
    </section>
  );
}
