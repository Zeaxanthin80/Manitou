import Image from "next/image";
import Link from "next/link";

import { buttonClasses } from "@/components/ui/button";
import { storeConfig } from "@/lib/store-config";

/**
 * The front page's opening: one full-bleed photograph, one panel of copy.
 *
 * **This deliberately overrides the "one big, quiet statement" direction** the
 * home page carried through Phase 3. That direction was a store name in 44px
 * Archivo Black over a tagline, and it made sense before there was a wordmark
 * in the header directly above it. Now it repeated the masthead, and a shop that
 * opens by saying its own name twice reads as a template. The photograph does
 * what the name was doing; the wordmark keeps the name.
 *
 * **Every word comes from `store-config.json`** (`home.featured`), for the same
 * reason `store.tagline` did: a clone must not edit a component to change its
 * pitch. The block already had an eyebrow, heading, body, button label and a
 * category slug for the featured-series band this replaces -- the hero is that
 * band promoted to lead, so the config shape did not change.
 *
 * **The copy sits in a panel, not on the photograph.** Text laid straight over
 * a photo is legible exactly as long as the photo stays light where the text is,
 * and the photo is a config value that will change. A `bg-surface` panel is
 * legible over anything. On a phone the panel stacks below the image and pulls
 * up over its bottom edge; above `wide:` it sits bottom-left inside the same
 * content column the rest of the page uses, so the copy lines up with the grid
 * beneath it rather than floating at the viewport's edge.
 *
 * The heading is the page's `<h1>`. The store name is carried by the wordmark's
 * alt text and by `<title>`; a heading that says what the store is *leading
 * with* is more useful to a reader and a crawler than one that repeats the tab.
 */
export function Hero() {
  // Widened from the generated `as const` literals, as the band did: the type
  // is regenerated from the JSON, so `category` types as its current value and
  // a literal-typed check would read as always-true.
  const featured: {
    category: string;
    eyebrow: string;
    heading: string;
    body: string;
    cta: string;
    image: string;
    image_alt: string;
  } = storeConfig.home.featured;

  // Empty category means "not leading with anything": no hero, and the page is
  // the plain catalogue. Same convention as `store.logo` -- the key stays, the
  // value empties -- so a clone switches it off without touching code.
  if (!featured.category) return null;

  return (
    <section aria-labelledby="hero-heading" className="relative">
      {/* Portrait on a phone, wide on a desktop. A 3:2 source with its subject
          centred crops acceptably into both; if a future photograph doesn't,
          the fix is a second <Image> art-directed with wide:hidden / hidden
          wide:block, not a change here. */}
      <div className="relative aspect-[4/5] wide:aspect-[2/1]">
        <Image
          src={featured.image}
          alt={featured.image_alt}
          fill
          sizes="100vw"
          // The largest thing above the fold on the busiest page: the LCP
          // element. Worth the preload.
          priority
          className="object-cover"
        />
      </div>

      {/* In normal flow below the image on a phone, pulled up by -mt-10 so the
          panel breaks the photograph's bottom edge. Above wide: the wrapper is
          absolute at the bottom of the section and shares the page's content
          column, so the panel's left edge lines up with the grid below. */}
      <div className="mx-auto max-w-6xl px-6 wide:absolute wide:inset-x-0 wide:bottom-0">
        <div className="-mt-10 rounded-md border border-border bg-surface p-6 shadow-md wide:mb-10 wide:mt-0 wide:max-w-md wide:p-8">
          {/* Merchandising is what the accent token is for; this and the active
              nav item are its two appearances on the page. */}
          <p className="font-body text-xs uppercase tracking-tight text-accent">
            {featured.eyebrow}
          </p>
          <h1
            id="hero-heading"
            className="mt-3 font-display text-2xl uppercase leading-none tracking-tight text-text wide:text-3xl"
          >
            {featured.heading}
          </h1>
          <p className="mt-4 max-w-prose font-body text-sm text-muted wide:text-base">
            {featured.body}
          </p>
          <Link
            href={`/categories/${featured.category}`}
            className={buttonClasses({ className: "mt-6 inline-flex" })}
          >
            {featured.cta}
          </Link>
        </div>
      </div>
    </section>
  );
}
