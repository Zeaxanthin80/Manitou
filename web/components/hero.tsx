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
 * **The panel sits on the photograph at every width, and it is translucent.**
 * The first version stacked it below the image on a phone and pulled it up by
 * 40px to "break the frame" -- and the frame won: the image wrapper is
 * `relative` and the panel's wasn't, so a positioned sibling painted over an
 * in-flow one and the overlap, eyebrow included, was hidden under the
 * photograph. Absolute at every width removes the bug and the trick together.
 * `bg-surface/80` with a backdrop blur keeps the copy legible over any part of
 * any photograph while still reading as one composition rather than a card
 * pasted on top; the tokens are unchanged, only their alpha.
 *
 * The frame is 3:4 on a phone -- taller than the 4:5 the tiles use -- so the
 * garments still show above a panel that covers roughly the lower 45%.
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
      {/* Portrait on a phone, wide on a desktop. A 3:2 source composed with its
          subject in the upper right and empty backdrop lower left crops into
          both without covering the garments; the photograph is generated to
          that brief, and a future one that isn't gets a second art-directed
          <Image> rather than a change here. */}
      {/* max-h-[75svh] above wide: an aspect ratio alone scales with the
          viewport's WIDTH, and on a 1920x1080 desktop 2:1 is 960px -- the hero
          filled the screen and pushed its own button below the fold. Capped at
          three-quarters of the small viewport height, the panel and its call to
          action are always in the first screen, whatever the monitor. The
          aspect ratio still governs narrower windows, where it never exceeds
          the cap. (svh: the height with browser chrome shown, so a phone's
          collapsing address bar cannot make it jump.)

          w-full is load-bearing, not decoration. With the width left auto, CSS
          transfers a max-height THROUGH an aspect ratio into a max-width, so
          the box kept 2:1 and shrank sideways instead -- 682px tall, 1364px
          wide, and a bare strip of page down the right of a 1920px monitor. A
          definite width is what makes the height clamp and the ratio yield. */}
      <div className="relative w-full aspect-[3/4] wide:aspect-[2/1] wide:max-h-[75svh]">
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

      {/* Absolute at every width. On a phone the panel keeps the page's 24px
          gutter; above wide: the wrapper spans the section and the inner column
          is the same max-w-6xl the grid uses, so the panel's left edge lines up
          with everything below it. */}
      <div className="absolute inset-x-6 bottom-6 wide:inset-x-0 wide:bottom-10">
        <div className="mx-auto max-w-6xl wide:px-6">
          <div className="rounded-md border border-border/60 bg-surface/80 p-6 shadow-lg backdrop-blur-md wide:max-w-md wide:p-8">
            {/* Merchandising is what the accent token is for; this and the
                active nav item are its two appearances on the page. */}
            <p className="font-body text-xs uppercase tracking-wide text-accent">
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
      </div>
    </section>
  );
}
